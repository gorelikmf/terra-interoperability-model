#!/usr/bin/env python

"""Create a basic CLI tool that parses the arg list defined in the spec
(as linked in the parent epic) and hands off the args to a stub driver method
"""

import argparse
import json
import logging
import sys
from os import path

from rdflib import Graph, Namespace, OWL, RDFS

Terra = Namespace("http://datamodel.terra.bio/TerraDCAT_ap#")
# the builtin RDFLIB PROV NS does not define 'definition' for unknown reasons, hence this ad hoc def
Prov = Namespace("http://www.w3.org/ns/prov#")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def get_arguments():
    """Arguments defined in spec
    1) a path to the data model *.TTL file
    2) a "class file" (newline delimited list of strings that correspond to RDF classes)
    """
    parser = argparse.ArgumentParser(description='Process data model export')
    parser.add_argument(
        '-f',
        '--file-path',
        help="path to the data model e.g.: 'src/terra-core/TerraDCAT-AP.ttl'",
        required=True)
    parser.add_argument(
        '-l',
        '--class-list',
        nargs='+',
        help="a class listing string e.g.: 'DataCollection BiomedicalResearch'")
    parser.add_argument('-c', '--class-path', help="a class listing file e.g.: 'class_name.txt'")
    args = parser.parse_args()

    if args.class_list is None and args.class_path is None:
        logging.error("Provide a class_list 'l' or class_path 'c' argument")
        sys.exit(1)
    elif args.class_list and args.class_path:
        logging.error("Provide a single class_list argument")
        sys.exit(1)
    elif args.class_list:
        return args.file_path, args.class_list
    elif args.class_path:
        class_list = []
        class_count = 0
        with open(args.class_path, 'r') as class_file:
            for class_count, line in enumerate(class_file):
                strip_line = line.strip()
                if not strip_line:
                    continue
                class_list.append(strip_line)
        logging.info(f"{class_count} classes parsed from {args.class_path}")
        logging.info(f"class_list: {class_list}")
        return args.file_path, class_list
    else:
        logging.error("Error parsing arguments, please try again...")


def ttl_to_json(file_path, class_name):
    """
    Reads ttl file from given file_path and pulls properties for the given class_name
    :param file_path: File path to ttl file to read
    :param class_name: Class name of class to grab properties from
    :return: Json schema of given class
    """
    with open(file_path, 'r') as ttl_file:
        rdf_term = Terra.term(class_name)
        # parse the file
        g = Graph()
        g.parse(ttl_file, format='turtle')
        properties = {
            "describedBy": {
                "description": "The URL reference to the JSON Schema that defines this object.",
                "type": "string"
            },
            "id": {
                "description": "UUID for this entity.",
                "type": "string"
            }
        }
        # 'required' properties are those with a cardinality of exactly 1, and the hardcoded 'id' property
        required = ['id', 'describedBy']

        # pull all RDF triples with the given rdf_term as the 'subject'
        term_triples = g.triples((rdf_term, None, None))
        for triple in term_triples:
            # any OWL equivalentClass predicate is a 'property'
            if triple[1] == OWL.equivalentClass:
                # the 'object' node reached via the equivalentClass predicate is a 'blank node' in
                # RDF; this node is anonymous and serves as a container for composite property information
                container_node = triple[2]
                cardinality = g.value(container_node, OWL.cardinality, None)
                prop = g.value(container_node, OWL.onProperty, None)
                # subject = container_node, predicate = OWL.onProperty, object)
                ref = prop.n3(g.namespace_manager)

                # this results in nulls for dct: terms
                rdfs_range_value = g.value(prop, RDFS.range)
                properties[prop.n3(g.namespace_manager)] = {
                    'description': ref,
                    '$ref': rdfs_range_value,
                }

                # should limit this to exactly 1 (take the cardinality seriously)
                if cardinality and cardinality.value == 1:
                    required.append(prop.n3(g.namespace_manager))

        json_schema = {
            '$id': rdf_term,
            '$schema': "http://json-schema.org/draft-07/schema#/",
            'title': g.value(rdf_term, RDFS.label),
            # json convention uses a "description" field as the definition
            'description': str(g.value(rdf_term, Prov.definition)),
            'definitions': {},
            'type': 'object',
            'additionalProperties': True,
            'properties': properties,
            'required': required
        }
        return json_schema


def rdf_to_json(file_path, class_list):
    """
    Function to convert RDF to JSON and store the class names with their schemas in a dictionary
    :param file_path: File Path to RDF
    :param class_list: List of classes to parse
    :return: Dictionary {key=class_name : value=json_schema}
    """
    json_schema_list = {class_name: ttl_to_json(file_path, class_name) for class_name in class_list}
    return json_schema_list


def write_to_json(out_file_name, json_dict, key):
    with open(out_file_name, 'w') as f:
        logging.info(json.dumps(json_dict[key], indent=4))
        json.dump(json_dict[key], f)


def main():
    # get CLI arguments
    file_path, class_list = get_arguments()
    # invoke driver to transform RDF to JSON
    json_dict = rdf_to_json(file_path, class_list)
    # write one file per class provided
    for key in json_dict:
        out_file_name = f"{key}.json"
        if path.exists(out_file_name):
            rewrite = input(out_file_name + " already exists. Overwrite? (y/n)")
            if rewrite == "y":
                write_to_json(out_file_name, json_dict, key)
        else:
            write_to_json(out_file_name, json_dict, key)


if __name__ == "__main__":
    main()
