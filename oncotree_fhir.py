"""convert Oncotree to HL7 FHIR CodeSystem resources
"""

import sys
import json
import argparse
import os
import textwrap
from csv import DictWriter
from typing import Dict, List, Tuple
import requests
from fhir.resources.codesystem import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptProperty,
)
from tqdm import tqdm


def parse_args(print_args: bool = True):
    """create the argument parser

    Args:
        print_args (bool, optional): If true, the arguments will
        be printed to stdout after parsing. Defaults to True.

    Returns:
        argparse.Namespace: the parsed arguments as a Namespace object
    """

    parser = argparse.ArgumentParser(
        prog="python oncotree-fhir.py",
        description="convert Oncotree to a HL7 FHIR CodeSystem resource",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version",
        "-v",
        help="version of Oncotree to download",
        default="oncotree_latest_stable",
    )
    parser.add_argument(
        "--url",
        "-u",
        help="Endpoint for Oncotree API",
        default="http://oncotree.mskcc.org/api",
        type=lambda x: x.rstrip("/"),
    )
    parser.add_argument(
        "--output",
        "-o",
        help="output file in JSON format. $version is replaced with the version string in filename",
        default=os.path.join(".", "$version.json"),
        type=str,
    )
    parser.add_argument(
        "--canonical",
        help="canonical url of the CodeSystem to generate. For the undated versions, the version string will be appended to this URL",
        default="http://oncotree.mskcc.org/fhir/CodeSystem",
    )
    parser.add_argument(
        "--valueset",
        help="canonical url of the implicit ValueSet with all codes to generate",
        default="http://oncotree.mskcc.org/fhir/ValueSet",
    )
    parser.add_argument(
        "--write-tsv",
        help="write the CodeSystem as a TSV file suitable for import into CSIRO's Snapper tool, helpful when creating ConceptMaps or ValueSets referencing Oncotree.",
        action="store_true"
    )
    parser.add_argument(
        "--tsv-output",
        default=os.path.join(".", "$version.tsv"),
        help="output file in TSV format (if --write-tsv given). $version is replaced with the version string in filename"
    )
    parser.add_argument(
        "action",
        default="convert",
        # default="versions",
        nargs="?",
        choices=["versions", "convert", "convert-all"],
        help="action to carry out",
    )

    args = parser.parse_args()

    if print_args:
        for arg in vars(args):
            print(f" - {arg}: {getattr(args, arg)}")

    available_versions = get_versions(args)
    if args.version not in list(x["api_identifier"] for x in available_versions):
        parser.error(
            f"version '{args.version}' is not known to the endpoint {args.url}. Use the 'versions' operation to list the available versions"
        )

    if args.action == "convert-all":
        if not "$version" in args.output:
            parser.error(
                "When converting all the available versions of Oncotree, the '--output' parameter must contain a placeholder '$version' that is replaced with the respective version string."
            )

    return args


class TreeNode:
    """ a node in the version tree graph """

    def __init__(self, value: str = None, children: 'List[TreeNode]' = None):
        """create a tree node, perhaps with children

        Args:
            value (str, optional): the text value of the node. Defaults to None.
            children (List[TreeNode], optional): the children of the node. Defaults to None.
        """
        if children is None:
            children = []
        self.value, self.children = value, children


def pprint_tree(node: TreeNode, file=None, _prefix="", _last=True, width=70):
    """Pretty-print a tree of nodes, from https://vallentin.dev/2016/11/29/pretty-print-tree

    Args:
        node ([type]): the root node
        file ([type], optional): File to pass to print(). Defaults to None.
        _prefix (str, optional): internal for recursive calls. Defaults to "".
        _last (bool, optional): internal for recursive calls. Defaults to True.
    """

    def wrap_to_width(val: str) -> str:
        wrapped_value = textwrap.wrap(val, width=width)
        if len(wrapped_value) > 1:
            join_wrapped_value = "\n".join(wrapped_value[1:])
            return (
                wrapped_value[0]
                + "\n"
                + textwrap.indent(join_wrapped_value, " " * (len(_prefix) + 3))
            )
        else:
            return wrapped_value[0]

    filled_value = wrap_to_width(node.value)
    print(_prefix, "`- " if _last else "|- ", filled_value, sep="", file=file)
    _prefix += "   " if _last else "|  "
    child_count = len(node.children)
    for i, child in enumerate(node.children):
        _last = i == (child_count - 1)
        pprint_tree(child, file, _prefix, _last)


def get_versions(args: argparse.Namespace) -> List[Dict]:
    """get the list of versions from the respective OncoTree endpoint

    Args:
        args (argparse.Namespace): the command line args

    Returns:
        List[Dict]: the list of versions as a (JSON) dict.
    """
    endpoint = f"{args.url}/versions"
    rx = requests.get(endpoint).json()
    rx.sort(key=lambda x: x["release_date"], reverse=True)
    return rx


def convert_oncotree(args: argparse.Namespace, version: str = None) -> CodeSystem:
    """convert the oncotree system with given version to FHIR

    Args:
        args (argparse.Namespace): the command line args
        version (str, optional): the version string Defaults to None. If not specified, args.version is used

    Returns:
        CodeSystem: the code system in FHIR R4 format
    """
    if version is None:
        version = args.version

    endpoint = f"{args.url}/tumorTypes?version={version}"
    rx = requests.get(endpoint)
    with open(os.path.join(".", "oncotree.tmp.json"), "w") as f:
        json.dump(rx.json(), f, indent=2)

    date_of_version = date_for_version_string(version)
    valueset_url = args.valueset.rstrip("/")
    codesystem_url = args.canonical.rstrip("/")
    name = "oncotree"
    title = "OncoTree"

    if version in [
        "oncotree_latest_stable",
        "oncotree_candidate_release",
        "oncotree_development",
        "oncotree_legacy_1.1",
    ]:
        version = version.replace("_", "-")
        codesystem_url += "/" + "snapshot"
        valueset_url += "/" + "snapshot"
        name = "oncotree-snapshot"
        title = "OncoTree Snapshot"
    else:
        version = version.replace("oncotree_", "").replace("_", "")

    print(
        f"getting {version} (released {date_of_version}) from {endpoint}")
    print()

    json_dict = {
        "resourceType": "CodeSystem",
        "id": version.replace("_", "-"),
        "url": codesystem_url,
        "valueSet": valueset_url,
        "status": "draft",
        "content": "complete",
        "name": name,
        "title": title,
        "version": version,
        "date": date_of_version,
        "hierarchyMeaning": "is-a",
        "property": [
            {
                "code": "color",
                "description": "Color in the Oncotree Visualisation",
                "type": "string",
            },
            {
                "code": "level",
                "description": "Level in the Oncotree hierarchy",
                "type": "integer",
            },
            {
                "code": "umls",
                "description": "Linked UMLS concept",
                "type": "string",
            },
            {
                "code": "nci",
                "description": "Linked NCI concept",
                "type": "string",
            },
        ],
        "concept": [],
    }
    print(json.dumps(json_dict))
    cs = CodeSystem(json_dict)
    print()
    print("Converting concepts...")
    sys.stdout.flush()
    for concept in tqdm(rx.json()):
        fhir_concept = convert_concept(concept)
        cs.concept.append(fhir_concept)
    return cs


def convert_concept(oncotree_concept: Dict) -> CodeSystemConcept:
    """convert the oncotree concept to a FHIR R4 CodeSystem concept

    Args:
        oncotree_concept (Dict): the element from the Oncotree API to convert

    Returns:
        CodeSystemConcept: the element in FHIR R4, with properties
    """
    concept = CodeSystemConcept(
        {
            "code": oncotree_concept["code"],
            "display": oncotree_concept["name"],
            "property": [],
        }
    )

    concept.property.append(
        CodeSystemConceptProperty(
            {"code": "level", "valueInteger": oncotree_concept["level"]}
        )
    )

    if "color" in oncotree_concept and oncotree_concept["color"] is not None:
        concept.property.append(
            CodeSystemConceptProperty(
                {"code": "color", "valueString": oncotree_concept["color"]}
            )
        )

    if "parent" in oncotree_concept and oncotree_concept["parent"] is not None:
        concept.property.append(
            CodeSystemConceptProperty(
                {"code": "parent", "valueCode": oncotree_concept["parent"]}
            )
        )

    if len(oncotree_concept["externalReferences"]) > 0:
        if "UMLS" in oncotree_concept["externalReferences"]:
            concept.property.append(
                CodeSystemConceptProperty(
                    {
                        "code": "umls",
                        "valueString": ", ".join(
                            oncotree_concept["externalReferences"]["UMLS"]
                        ),
                        # there is at least on concept, SRCCR, that has multiple UMLS and NCI references
                    }
                )
            )
        if "NCI" in oncotree_concept["externalReferences"]:
            concept.property.append(
                CodeSystemConceptProperty(
                    {
                        "code": "nci",
                        "valueString": ", ".join(
                            oncotree_concept["externalReferences"]["NCI"]
                        ),
                    }
                )
            )
    return concept


def write_codesystem(args: argparse.Namespace, cs: CodeSystem, version: str = None):
    """write the codesystem to a JSON file, as defined by the args

    Args:
        args (argparse.Namespace): the command line args
        cs (CodeSystem): the FHIR code system to write
        version (str): the version string. Default to None. If not specified, args.version is used.
    """
    if version is None:
        version = args.version
    _, filepath = sanitize_filename(args.output, version)
    with open(filepath, "w") as jf:
        json.dump(cs.as_json(), jf, indent=2)
    print(f"Wrote output to {filepath}")


def sanitize_filename(fn: str, version: str) -> Tuple[str, str]:
    """clean up the filename, add the version string if required (replacing $version) and return the full path to the output file

    Args:
        fn (str): the filename to sanitize
        version (str): the version string to add, replacing $version

    Returns:
        Tuple[str, str]: (filename, filepath)
    """
    filename = os.path.expanduser(fn).replace("$version", version)
    if os.path.dirname(os.path.abspath(filename)) == os.path.abspath("."):
        filepath = filename
    else:
        filepath = os.path.join(
            os.path.abspath(os.path.dirname(filename)), os.path.basename(filename))
    return filename, filepath


def date_for_version_string(version_string: str) -> str:
    """find the date a version was released from the versions API response

    Args:
        version_string (str): the version string to look up

    Returns:
        str: the release date of the version string, in ISO 8601 format, i.e. "YYYY-MM-DD"
    """
    return [v for v in versions if v["api_identifier"] == version_string][0][
        "release_date"
    ]


def print_versions(versions: List[str]):
    """print all available version from the given oncotree endpoint as a pretty tree

    Args:
        versions (List[str]): the list of versions to pretty-print
    """
    endpoint = f"{args.url}/versions"
    visible_versions = [x for x in versions if x["visible"]]
    invisible_versions = [x for x in versions if not x["visible"]]
    root_node = TreeNode(f"available versions from {endpoint}")

    def print_version_strings(prefix: str, versions: List[Dict]) -> TreeNode:
        """helper function to print a version string with a given, common, prefix

        Args:
            prefix (str): the prefix, for example "2020 versions" or "current releases", that the releases are grouped under
            versions (List[Dict]): the list of versions to pretty-print under the prefix

        Returns:
            TreeNode: the tree node containing the prefix with respective child nodes
        """
        root = TreeNode(prefix)
        for version in versions:
            node = TreeNode(
                version["api_identifier"],
                [
                    TreeNode(f"released {version['release_date']}"),
                    TreeNode(version["description"]),
                ],
            )
            root.children.append(node)
        return root

    root_node.children.append(
        print_version_strings("current/visible versions", visible_versions)
    )
    root_node.children.append(
        print_version_strings("invisible versions", invisible_versions)
    )
    pprint_tree(root_node)


def write_tsv_codesystem(args: argparse.Namespace, cs: CodeSystem, version: str) -> None:
    """write the codesystem to a JSON file, as defined by the args (or return immediately if no TSV files should be written)

    Args:
        args (argparse.Namespace): the command line args
        cs (CodeSystem): the FHIR CS to write
        version (str): the version string of this file

    Returns:
        None
    """
    if not args.write_tsv:
        return None
    fieldnames = ["code", "label", "parent"]

    def parent_for_code(c: str) -> str:
        """helper function to return the parent of a FHIR code system concept

        Args:
            c (str): the concept to extract the property for

        Returns:
            str: the code of the parent, or None
        """
        p = [p for p in c.property if p.code == "parent"]
        if any(p):
            return p[0].valueCode
        return None

    tsv_codes = [{"code": c.code, "label": c.display,
                  "parent": parent_for_code(c)} for c in cs.concept]
    tsv_codes.sort(key=lambda c: c["code"])
    #tsv_filename = args.tsv_output.replace("$version", version)
    tsv_filename, tsv_path = sanitize_filename(args.tsv_output, version)
    with open(tsv_path, "w") as csvfile:
        writer = DictWriter(csvfile, fieldnames=fieldnames, delimiter="\t")
        writer.writerows(tsv_codes)
    print(f"wrote TSV to {tsv_filename}")


if __name__ == "__main__":
    args = parse_args()
    print("\n")
    versions = get_versions(args)
    if args.action == "versions":
        print_versions(versions)
    elif args.action == "convert":
        cs = convert_oncotree(args)
        write_codesystem(args, cs)
        write_tsv_codesystem(args, cs, args.version)
    elif args.action == "convert-all":
        for v in versions:
            version = v["api_identifier"]
            print(f"Getting version {version}")
            cs = convert_oncotree(args, version)
            write_codesystem(args, cs, version)
            write_tsv_codesystem(args, cs, version)
            print("\n----\n")
            sys.stdout.flush()
