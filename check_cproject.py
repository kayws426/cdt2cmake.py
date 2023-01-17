#!/usr/bin/python3

import io
import os
import sys
from typing import List, Set, Tuple, Dict
import xml.etree.ElementTree as elemTree
from lxml import objectify

__version__ = "0.0.1"

def debug_print(msg, *args):
    return # print(msg, *args)


class config_info:
    def __init__(self, node=None):
        self.OPT_CODEGEN_VERSION = {}
        self.OPT_TAGS = {}
        self.COMPILER_OPTIONS = {}
        self.LINKER_OPTIONS = {}
        self.HEX_OPTIONS = {}
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
                    self.OPT_CODEGEN_VERSION[option.attrib['id']] = option.attrib['value']
                    debug_print("** self.OPT_CODEGEN_VERSION:", self.OPT_CODEGEN_VERSION)
                if "OPT_TAGS" in option.attrib['id']:
                    for listoptval in option.findall('listOptionValue'):
                        items = listoptval.attrib['value'].split('=')
                        self.OPT_TAGS[items[0]] = items[1]
                    debug_print("** self.OPT_TAGS:", self.OPT_TAGS)

            self.TOOLCHAIN_OPTIONS = self.parse_tool_options(toolChain)
            debug_print("** self.TOOLCHAIN_OPTIONS:", self.TOOLCHAIN_OPTIONS)

            # parse toolChain/tool
            for tool in toolChain.findall('./tool'):
                tool_id_temp = tool.attrib['id'].lower()
                if "compiler" in tool_id_temp:
                    self.COMPILER_OPTIONS[tool.attrib['id']] = self.parse_tool_options(tool)
                    debug_print("** self.COMPILER_OPTIONS:", self.COMPILER_OPTIONS)
                if "linker" in tool_id_temp:
                    self.LINKER_OPTIONS[tool.attrib['id']] = self.parse_tool_options(tool)
                    debug_print("** self.LINKER_OPTIONS:", self.LINKER_OPTIONS)
                if "hex" in tool_id_temp:
                    self.HEX_OPTIONS[tool.attrib['id']] = self.parse_tool_options(tool)
                    debug_print("** self.HEX_OPTIONS:", self.HEX_OPTIONS)

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


class cdt_project:
    PROJECT_DIR = '.'
    WORKSPACE_DIR = '..'
    configs = {}
    srcs = []
    project_xml = None
    cproject_xml = None
    ccsproject_xml = None

    def _get_project_xml(self):
        if self.project_xml is None:
            project_filepath = os.path.join(self.PROJECT_DIR, ".project")
            self.project_xml = elemTree.parse(project_filepath)
        return self.project_xml

    def _get_cproject_xml(self):
        if self.cproject_xml is None:
            cproject_filepath = os.path.join(self.PROJECT_DIR, ".cproject")
            self.cproject_xml = elemTree.parse(cproject_filepath)
        return self.cproject_xml

    def __init__(self, PROJECT_DIR: str, WORKSPACE_DIR: str = None):
        WORKSPACE_DIR = WORKSPACE_DIR or os.path.join(PROJECT_DIR, '..')
        self.PROJECT_DIR = PROJECT_DIR
        self.WORKSPACE_DIR = WORKSPACE_DIR
        self.srcs = self.get_srcs()
        self.configs = self.get_configs()

    def get_project_name(self) -> str:
        project_xml = self._get_project_xml()
        name_node = project_xml.find("./name")
        return name_node.text

    def get_srcs(self) -> str:
        project_xml = self._get_project_xml()
        srcs = []
        linked_resources = project_xml.find("./linkedResources")
        for resource in linked_resources:
            uri = resource.find('locationURI')
            srcs.append(uri.text.strip())
            # print(uri.text.strip())
        self.srcs = srcs

    def get_configs(self) -> Dict:
        proj_name = self.get_project_name()

        cproject_filepath = os.path.join(self.PROJECT_DIR, ".cproject")
        cproject_xml = elemTree.parse(cproject_filepath)

        configs = {}
        config_nodes = cproject_xml.findall(".//storageModule[@moduleId='cdtBuildSystem']/configuration[@name]")
        for config_node in config_nodes:
            config_name = config_node.attrib['name']
            configs[config_name] = {k:v for k,v in config_node.attrib.items()}  # copy atributes
            configs[config_name]['config_info'] = config_info(config_node)
            configs[config_name]['PROJECT_NAME'] = proj_name
            configs[config_name]['PROJECT_DIR'] = self.PROJECT_DIR

        # for config_name, config in configs.items():
        #     print(f"-- proj name: {config['PROJECT_NAME']}")
        #     print(f"  -- config: {config_name} (artifactName: {config['artifactName']})")
        #     print(f"    -- {config}")

        return configs


class cmake_generator:
    target_filename = 'CMakeLists.txt'
    target_dir = '.'
    variable_dict = None

    def set_gen_target_dir(self, path: str) -> None:
        self.target_dir = path

    def gether_vaiable(self, config: config_info) -> None:
        if self.variable_dict is None:
            self.variable_dict ={}
            self.variable_dict['${ProjName}'] = config['PROJECT_NAME']
            self.variable_dict['${workspace_loc}'] = config['PROJECT_DIR'] + '/..'
            self.variable_dict['${PROJECT_ROOT}'] = config['PROJECT_DIR']
            self.variable_dict['${PROJECT_LOC}'] = config['PROJECT_DIR']
            # debug_print('variable_dict', self.variable_dict)

    def expand_variable(self, text: str) -> str:
        if text[0] == '"' and text[-1] == '"' and text.count('"') == 2:
            text = text[1:-1]

        if '${workspace_loc:/${ProjName}' in text and text[-1] == '}':
            text = text[0:-1].replace('${workspace_loc:/${ProjName}', '${PROJECT_LOC}')

        if text[-1] == '}' and ':' in text:
            tmp = text.split(':')
            text = tmp[0] + '}' + tmp[1][0:-1]

        for k,v in self.variable_dict.items():
            text = text.replace(k, v)

        return text
    
    def get_src_files(self, config: config_info, current_target_name: str) -> List[str]:
        start_dir = config['PROJECT_DIR']
        file_list = []
        # start walk dir into start_dir and gether files with ['.c', '.asm'] extention
        for root, dirs, files in os.walk(start_dir):
            for file in files:
                if file.endswith('.c') or file.endswith('.asm'):
                    if "CMake" not in file and "CompilerId." not in file:
                        file_list.append(os.path.join(root, file).replace('\\','/'))
        return file_list

    def generate(self, config_name: str, config: config_info, outfile) -> None:
        self.gether_vaiable(config)

        config_info = config['config_info']
        current_target_name = config['PROJECT_NAME']

        outfile.write('cmake_minimum_required(VERSION 3.5)\n')

        outfile.write('\n')
        outfile.write(f'project({current_target_name})\n')

        outfile.write('\n')
        outfile.write('set(CG_TOOL_ROOT "C:/ti/ccsv7/tools/compiler/ti-cgt-c2000_16.9.1.LTS")\n')

        outfile.write('\n')
        outfile.write('add_compile_options(-v28 -ml -mt --cla_support=cla1 --float_support=fpu32 --tmu_support=tmu0 --vcu_support=vcu2 -O0 --fp_mode=relaxed)\n')

        SRC_FILES = self.get_src_files(config, current_target_name)

        if SRC_FILES is not None and len(SRC_FILES) > 0:
            outfile.write(f'\nadd_executable({current_target_name}')
            for src_file in SRC_FILES:
                outfile.write(f"\n\t{src_file}")
            outfile.write('\n)\n')

            for tool_id, tool_options in config_info.COMPILER_OPTIONS.items():
                outstrlist = []
                for item in (tool_options.get('symbols_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                for item in (tool_options.get('DEFINE_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_compile_definitions({current_target_name} PUBLIC")
                    outfile.write(''.join(outstrlist))
                    outfile.write('\n)\n')

                outstrlist = []
                for item in (tool_options.get('paths_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                for item in (tool_options.get('INCLUDE_PATH_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_include_directories({current_target_name} PUBLIC")
                    outfile.write(''.join(outstrlist))
                    outfile.write('\n)\n')

            for tool_id, tool_options in config_info.LINKER_OPTIONS.items():
                outstrlist = []
                for item in (tool_options.get('paths_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                for item in (tool_options.get('SEARCH_PATH_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_link_directories({current_target_name} PUBLIC")
                    outfile.write(''.join(outstrlist))
                    outfile.write('\n)\n')

                outstrlist = []
                for item in (tool_options.get('input_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                for item in (tool_options.get('LIBRARY_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"\n\t{item_str}")
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_link_libraries({current_target_name} PUBLIC")
                    outfile.write(''.join(outstrlist))
                    outfile.write('\n)\n')

            #
        #


def main():
    if len(os.sys.argv) > 1 and len(os.sys.argv[1]) > 0:
        PROJECT_DIR = os.sys.argv[1]
    else:
        PROJECT_DIR = "."

    cdt_prj = cdt_project(PROJECT_DIR)

    # generate
    outfile = open('CMakeLists.txt', "w")
    # outfile = sys.stdout

    for config_name, config in cdt_prj.configs.items():
        generator = cmake_generator()
        generator.generate(config_name, config, outfile)
        break


if __name__ == "__main__":
    main()
