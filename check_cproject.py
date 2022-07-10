#!/usr/bin/python3

import os
from typing import List, Set, Tuple, Dict
import xml.etree.ElementTree as elemTree
from lxml import objectify

__version__ = "0.0.1"

def debug_print(msg, *args):
    return print(msg, *args)


class config_info:
    def __init__(self, node=None):
        if node:
            self.parse(node)

    def parse(self, config_node):
        self.name = config_node.attrib['name']
        toolChain = config_node.find('.//toolChain')
        if toolChain:
            self.toolChain = {k:v for k,v in toolChain.attrib.items()}  # copy atributes

            # parse toolChain/option
            for option in toolChain.findall('./option'):
                if "OPT_CODEGEN_VERSION" in option.attrib['id']:
                    self.OPT_CODEGEN_VERSION = option.attrib['value']
                    debug_print("** self.OPT_CODEGEN_VERSION:",  self.OPT_CODEGEN_VERSION)
                if "OPT_TAGS" in option.attrib['id']:
                    self.OPT_TAGS = {}
                    for listoptval in option.findall('listOptionValue'):
                        items = listoptval.attrib['value'].split('=')
                        self.OPT_TAGS[items[0]] = items[1]
                    debug_print("** self.OPT_TAGS:",  self.OPT_TAGS)

            self.TOOLCHAIN_OPTIONS = self.parse_tool_options(toolChain)
            debug_print("** self.TOOLCHAIN_OPTIONS:",  self.TOOLCHAIN_OPTIONS)

            # parse toolChain/tool
            for tool in toolChain.findall('./tool'):
                tool_id_temp = tool.attrib['id'].lower()
                if "compiler" in tool_id_temp:
                    self.COMPILER_OPTIONS = self.parse_tool_options(tool)
                    debug_print("** self.COMPILER_OPTIONS:",  self.COMPILER_OPTIONS)
                if "linker" in tool_id_temp:
                    self.LINKER_OPTIONS = self.parse_tool_options(tool)
                    debug_print("** self.LINKER_OPTIONS:",  self.LINKER_OPTIONS)
                if "hex" in tool_id_temp:
                    self.HEX_OPTIONS = self.parse_tool_options(tool)
                    debug_print("** self.HEX_OPTIONS:",  self.HEX_OPTIONS)

    @staticmethod
    def parse_tool_options(tool_node) -> Dict:
        tool_options = {}
        for option in tool_node.findall('./option'):
            opt_key = option.attrib['id'].split('.')[-2]
            opt_val = option.attrib.get('value', None)
            if opt_val:
                tool_options[opt_key] = opt_val
            else:
                list_options = []
                tool_option_subitems = []
                for listoptval in option.findall('listOptionValue'):
                    list_options.append(listoptval.attrib['value'])
                    tool_option_subitems.append({k:v for k,v in listoptval.attrib.items()})  # copy atributes
                tool_options[opt_key] = list_options
                tool_options[opt_key + "_SUBITEMS"] = tool_option_subitems
            tool_options[opt_key + "_DICT"] = {k:v for k,v in option.attrib.items()}  # copy atributes
        return tool_options


def get_project_name(PROJECT_DIR: str) -> str:
    project_filepath = os.path.join(PROJECT_DIR, ".project")
    project_xml = elemTree.parse(project_filepath)
    name_node = project_xml.find("./name")
    proj_name = name_node.text
    return proj_name


def get_configs(PROJECT_DIR: str) -> Dict:
    cproject_filepath = os.path.join(PROJECT_DIR, ".cproject")
    cproject_xml = elemTree.parse(cproject_filepath)

    configs = {}
    config_nodes = cproject_xml.findall(".//storageModule[@moduleId='cdtBuildSystem']/configuration[@name]")
    for config_node in config_nodes:
        config_name = config_node.attrib['name']
        configs[config_name] = {k:v for k,v in config_node.attrib.items()}  # copy atributes
        configs[config_name]['config_info'] = config_info(config_node)
    return configs


def main():
    if len(os.sys.argv) > 1 and len(os.sys.argv[1]) > 0:
        PROJECT_DIR = os.sys.argv[1]
    else:
        PROJECT_DIR = "."

    proj_name = get_project_name(PROJECT_DIR)
    print(f"-- proj name: {proj_name}")

    configs = get_configs(PROJECT_DIR)
    for config_name, config in configs.items():
        print(f"  -- config: {config_name} (artifactName: {config['artifactName']})")
        print(f"    -- {config}")


if __name__ == "__main__":
    main()
