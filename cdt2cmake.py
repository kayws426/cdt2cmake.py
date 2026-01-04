#!/usr/bin/env python3

import io
import os
import sys
from typing import List, Set, Tuple, Dict
import xml.etree.ElementTree as elemTree
from lxml import objectify
from pathlib import Path

__version__ = "0.0.6"

def debug_print(msg, *args):
    return  # print(msg, *args)


def unquote_path(path: str) -> str:
    path = str(path)
    if path[0] == '"' and path[-1] == '"' and path.count('"') == 2:
        path = path[1:-1]
    return path


def quote_path(path: str, force=False) -> str:
    path = str(path)
    if force or (path[0] != '"' and ' ' in path):
        path = f'"{path}"'
    return path


def norm_path(pathstr: str) -> str:
    path = Path(pathstr).as_posix()
    if path[0] == '"' and path[-1] == '"' and path.count('"') == 2 and ' ' not in path:
        path = path[1:-1]
    return path


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
        folderInfo = config_node.find('.//folderInfo')

        toolChain = folderInfo.find('.//toolChain')
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

            targetPlatform = toolChain.find('./targetPlatform')
            self.TARGETPLATFORM = {k:v for k,v in targetPlatform.attrib.items()}  # copy atributes
            debug_print("** self.TARGETPLATFORM:", self.TARGETPLATFORM)

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

        self.FILEINFO = {}
        FILEINFO = {}
        fileInfos = config_node.findall('.//fileInfo')
        for fileInfo in fileInfos:
            FILEINFO_DICT = {k:v for k,v in fileInfo.attrib.items()}  # copy atributes
            temp_dict = dict(FILEINFO_DICT=FILEINFO_DICT)

            COMPILER_OPTIONS = {}
            LINKER_OPTIONS = {}
            # parse fileInfo/tool
            for tool in fileInfo.findall('./tool'):
                tool_id_temp = tool.attrib['id'].lower()
                if "compiler" in tool_id_temp:
                    COMPILER_OPTIONS[tool.attrib['id']] = self.parse_tool_options(tool)
                    debug_print("** fileInfo.COMPILER_OPTIONS:", COMPILER_OPTIONS)
                if "linker" in tool_id_temp:
                    LINKER_OPTIONS[tool.attrib['id']] = self.parse_tool_options(tool)
                    debug_print("** fileInfo.LINKER_OPTIONS:", LINKER_OPTIONS)
            temp_dict['COMPILER_OPTIONS'] = COMPILER_OPTIONS
            temp_dict['LINKER_OPTIONS'] = LINKER_OPTIONS
            FILEINFO[fileInfo.attrib['resourcePath']] = temp_dict
        self.FILEINFO = FILEINFO
        debug_print(FILEINFO)

        self.EXCLUDE_INFO = []
        EXCLUDE_INFO = []
        sourceEntries = config_node.findall('.//sourceEntries')
        for sourceEntry in sourceEntries:
            entries = config_node.findall('.//entry')
            for entry in entries:
                ei_item = {k:v for k,v in entry.attrib.items()}  # copy atributes
                ei_item['exclude_item_list'] = ei_item.get('excluding','').replace(';', '|').split('|')
                EXCLUDE_INFO.append(ei_item)
        self.EXCLUDE_INFO = EXCLUDE_INFO
        debug_print(EXCLUDE_INFO)

    @staticmethod
    def parse_tool_options(tool_node, tag_select_str:str = './option') -> Dict:
        tool_options = {}
        for option in tool_node.findall(tag_select_str):
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
    PROJECT_NAME = 'unkown_project'
    configs = {}
    SRCS = []
    RESOURCE_MAP = {}
    variable_dict0 = []
    variable_dict = []
    project_xml = None
    cproject_xml = None
    ccsproject_xml = None

    def _get_project_xml(self):
        if self.project_xml is None:
            project_filepath = Path(self.PROJECT_DIR, ".project")
            self.project_xml = elemTree.parse(project_filepath)
        return self.project_xml

    def _get_cproject_xml(self):
        if self.cproject_xml is None:
            cproject_filepath = Path(self.PROJECT_DIR, ".cproject")
            self.cproject_xml = elemTree.parse(cproject_filepath)
        return self.cproject_xml

    def __init__(self, PROJECT_DIR: str, WORKSPACE_DIR: str = None):
        WORKSPACE_DIR = WORKSPACE_DIR or Path(PROJECT_DIR, '..')
        self.PROJECT_DIR = norm_path(PROJECT_DIR)
        self.WORKSPACE_DIR = norm_path(WORKSPACE_DIR)
        #
        self.PROJECT_NAME = self._get_project_name()
        self._gether_vaiable()
        self.configs = self._get_configs()
        self.SRCS, self.RESOURCE_MAP = self._get_srcs()

    def _get_project_name(self) -> str:
        project_xml = self._get_project_xml()
        name_node = project_xml.find("./name")
        return name_node.text

    def _get_srcs(self) -> List[str]:
        project_xml = self._get_project_xml()
        srcs = []
        resource_map = {}
        linked_resources = project_xml.find("./linkedResources") or []
        for resource in linked_resources:
            name = resource.find('name').text.strip()
            type = int(resource.find('type').text.strip())
            uri = resource.find('locationURI')
            uri = resource.find('location') if uri is None else uri
            if uri is not None:
                resource_map[name] = uri
                if type == 1:
                    file_path = self.expand_variable(uri.text.strip())
                    file_path = norm_path(file_path)
                    srcs.append(file_path)
                if type == 2:
                    uri = self.expand_variable(uri.text.strip())
                    srcs.append('@linkedResources://' + uri)
        return srcs, resource_map

    def _get_configs(self) -> Dict:
        cproject_xml = self._get_cproject_xml()

        configs = {}
        config_nodes = cproject_xml.findall(".//storageModule[@moduleId='cdtBuildSystem']/configuration[@name]")
        for config_node in config_nodes:
            config_name = config_node.attrib['name']
            configs[config_name] = {k:v for k,v in config_node.attrib.items()}  # copy atributes
            configs[config_name]['config_info'] = config_info(config_node)
            configs[config_name]['PROJECT_NAME'] = self.PROJECT_NAME
            configs[config_name]['PROJECT_DIR'] = self.PROJECT_DIR

        # for config_name, config in configs.items():
        #     print(f"-- proj name: {config['PROJECT_NAME']}")
        #     print(f"  -- config: {config_name} (artifactName: {config['artifactName']})")
        #     print(f"    -- {config}")

        return configs

    def _gether_vaiable(self) -> None:
        if len(self.variable_dict0) == 0:
            self.variable_dict0 = {}
            for N in range(1, 21):
                PARENT_N_PROJECT_LOC = norm_path(Path(self.PROJECT_DIR, '.', '../' * N))
                self.variable_dict0[f'PARENT-{N}-PROJECT_LOC'] = PARENT_N_PROJECT_LOC
                PARENT_N_WORKSPACE_LOC = norm_path(Path(self.WORKSPACE_DIR, '.', '../' * N))
                self.variable_dict0[f'PARENT-{N}-WORKSPACE_LOC'] = PARENT_N_WORKSPACE_LOC

        if len(self.variable_dict) == 0:
            self.variable_dict = {}
            self.variable_dict['ProjName'] = self.PROJECT_NAME
            self.variable_dict['workspace_loc'] = self.WORKSPACE_DIR
            self.variable_dict['WORKSPACE_ROOT'] = self.WORKSPACE_DIR
            self.variable_dict['WORKSPACE_LOC'] = self.WORKSPACE_DIR
            self.variable_dict['PROJECT_ROOT'] = self.PROJECT_DIR
            self.variable_dict['PROJECT_LOC'] = self.PROJECT_DIR
            # debug_print('variable_dict', self.variable_dict)

    def expand_variable(self, text: str) -> str:
        is_quoted = False
        if text[0] == '"' and text[-1] == '"' and text.count('"') == 2:
            text = text[1:-1]
            is_quoted = True

        if '${workspace_loc:/${ProjName}' in text and text[-1] == '}':
            text = text[0:-1].replace('${workspace_loc:/${ProjName}', '${PROJECT_LOC}')

        if text[-1] == '}' and ':' in text:
            tmp = text.split(':')
            text = tmp[0] + '}' + tmp[1][0:-1]

        for k,v in self.variable_dict0.items():
            text = text.replace(f'${{{k}}}', v)
            text = text.replace(k, v)

        for k,v in self.variable_dict.items():
            text = text.replace(f'${{{k}}}', v)
            text = text.replace(k, v)

        if is_quoted:
            text = f'"{text}"'

        return text


class cmake_generator:
    target_filename = 'CMakeLists.txt'
    target_dir = '.'
    variable_dict = None

    def __init__(self, cdt_prj: cdt_project):
        self.cdt_prj = cdt_prj

    def set_gen_target_dir(self, path: str) -> None:
        self.target_dir = path

    def gether_vaiable(self, config: config_info) -> None:
        if self.variable_dict is None:
            self.variable_dict = {}
            # self.variable_dict['${ProjName}'] = config['PROJECT_NAME']
            # self.variable_dict['${workspace_loc}'] = config['PROJECT_DIR'] + '/..'
            # self.variable_dict['${PROJECT_ROOT}'] = config['PROJECT_DIR']
            # self.variable_dict['${PROJECT_LOC}'] = config['PROJECT_DIR']
            # debug_print('variable_dict', self.variable_dict)

    def expand_variable(self, text: str) -> str:
        text = self.cdt_prj.expand_variable(text)

        for k,v in self.variable_dict.items():
            text = text.replace(k, v)

        return text

    def path_from_dir_item(self, path: str) -> str:
        if path.startswith(self.cdt_prj.PROJECT_DIR):
            path = path.replace(self.cdt_prj.PROJECT_DIR, '${PROJECT_DIR}')
        return quote_path(path)

    def path_from_file_item(self, path: str) -> str:
        if path.startswith(self.cdt_prj.PROJECT_DIR):
            path = path.replace(self.cdt_prj.PROJECT_DIR, '${PROJECT_DIR}')
        return quote_path(path)

    def get_src_files(self, config: config_info, current_target_name: str, search_dir_arg: str = None) -> List[str]:
        config_info = config['config_info']
        if search_dir_arg is None:
            search_dir_arg = config['PROJECT_DIR']
        is_c2000 = 'C2000' in config_info.TARGETPLATFORM.get('superClass')

        # file_list = self.cdt_prj.SRCS
        file_list = []
        search_dirs = [search_dir_arg]

        for uri in self.cdt_prj.SRCS:
            if uri.startswith('@linkedResources://'):
                uri_dir = uri[len('@linkedResources://'):]
                search_dirs.append(uri_dir)
            else:
                file = uri
                if file.endswith('.c') or file.endswith('.cla') or file.endswith('.asm') or (is_c2000 and file.endswith('.cmd')):
                    file_list.append(file)

        for search_dir in search_dirs:
            # start walk dir into search_dir and gether files with ['.c', '.asm'] extention
            for root, dirs, files in os.walk(search_dir):
                for file in files:
                    if file.endswith('.c') or file.endswith('.cla') or file.endswith('.asm') or (is_c2000 and file.endswith('.cmd')):
                        if "CMake" not in file and "CompilerId." not in file:
                            file_path = Path(root, file)
                            file_path = norm_path(file_path)
                            file_list.append(file_path)
                            debug_print(file_path)
        return file_list

    def get_lib_files(self, config: config_info, current_target_name: str, search_dir_arg: str = None) -> List[str]:
        config_info = config['config_info']
        if search_dir_arg is None:
            search_dir_arg = config['PROJECT_DIR']
        is_c2000 = 'C2000' in config_info.TARGETPLATFORM.get('superClass')

        # file_list = self.cdt_prj.SRCS
        file_list = []
        search_dirs = [search_dir_arg]

        for uri in self.cdt_prj.SRCS:
            if uri.startswith('@linkedResources://'):
                uri_dir = uri[len('@linkedResources://'):]
                search_dirs.append(uri_dir)
            else:
                file = uri
                if file.endswith('.a') or file.endswith('.lib') or (is_c2000 and file.endswith('.cmd')):
                    file_list.append(file)

        for search_dir in search_dirs:
            # start walk dir into search_dir and gether files with ['.a', '.lib'] extention
            for root, dirs, files in os.walk(search_dir):
                for file in files:
                    if file.endswith('.a') or file.endswith('.lib') or (is_c2000 and file.endswith('.cmd')):
                        if "CMake" not in file and "CompilerId." not in file:
                            file_path = Path(root, file)
                            file_path = norm_path(file_path)
                            file_list.append(file_path)
                            debug_print(file_path)
        return file_list

    def generate(self, config_name: str, outfile) -> None:
        config = self.cdt_prj.configs.get(config_name)
        self.gether_vaiable(config)

        config_info = config['config_info']
        current_target_name = config['PROJECT_NAME']

        outfile.write('cmake_minimum_required(VERSION 3.18)\n')

        # print(config_info.TOOLCHAIN_OPTIONS.get('OPT_CODEGEN_VERSION_DICT'))
        # print(config_info.TARGETPLATFORM.get('superClass'))
        if config_info.TARGETPLATFORM.get('superClass'):
            OPT_CODEGEN_VERSION = config_info.TOOLCHAIN_OPTIONS.get('OPT_CODEGEN_VERSION')
            if OPT_CODEGEN_VERSION is None:
                OPT_CODEGEN_VERSION = 'unknown_version'
            if 'C2000' in config_info.TARGETPLATFORM.get('superClass'):
                c2000_opt_dict = {}
                c2000_opt_lines = []
                for tool_id, tool_options in config_info.COMPILER_OPTIONS.items():
                    c2000_opt_dict['LARGE_MEMORY_MODEL'] = (tool_options.get('LARGE_MEMORY_MODEL') or "true") == 'true'
                    c2000_opt_dict['UNIFIED_MEMORY'] = (tool_options.get('UNIFIED_MEMORY') or "true") == 'true'
                    c2000_opt_dict['SILICON_VERSION'] = (tool_options.get('SILICON_VERSION') or "SILICON_VERSION.28").split('.')[-1]
                    c2000_opt_dict['FLOAT_SUPPORT'] = (tool_options.get('FLOAT_SUPPORT') or "FLOAT_SUPPORT.fpu32").split('.')[-1]
                    c2000_opt_dict['CLA_SUPPORT'] = (tool_options.get('CLA_SUPPORT') or "CLA_SUPPORT.cla1").split('.')[-1]
                    c2000_opt_dict['VCU_SUPPORT'] = (tool_options.get('VCU_SUPPORT') or "VCU_SUPPORT.vcu2").split('.')[-1]
                    c2000_opt_dict['TMU_SUPPORT'] = (tool_options.get('TMU_SUPPORT') or "TMU_SUPPORT.tmu0").split('.')[-1]
                    if tool_options.get('OPT_LEVEL') is not None:
                        c2000_opt_dict['OPT_LEVEL'] = (tool_options.get('OPT_LEVEL') or "OPT_LEVEL.0").split('.')[-1]
                    if tool_options.get('OPT_FOR_SPEED') is not None:
                        c2000_opt_dict['OPT_FOR_SPEED'] = (tool_options.get('OPT_FOR_SPEED') or "OPT_FOR_SPEED.2").split('.')[-1]
                    c2000_opt_dict['FP_MODE'] = (tool_options.get('FP_MODE') or "FP_MODE.relaxed").split('.')[-1]
                    for k, v in c2000_opt_dict.items():
                        if v is True:
                            c2000_opt_lines.append("--{0}".format(k.lower()))
                        else:
                            c2000_opt_lines.append("--{0}={1}".format(k.lower(), str(v).lower()))
                    # end of for loop
                # end of for loop
                if len(c2000_opt_lines) > 0:
                    outfile.write('\nset(CMAKE_C2000_DEFAULT_COMPILE_FLAGS "{0}" CACHE STRING "")'.format(' '.join(c2000_opt_lines)))

                c2000_linker_opt_dict = {}
                c2000_linker_opt_lines = []
                for tool_id, tool_options in config_info.LINKER_OPTIONS.items():
                    if tool_options.get('STACK_SIZE') is not None:
                        c2000_linker_opt_dict['STACK_SIZE'] = (tool_options.get('STACK_SIZE') or "0x400")
                    if tool_options.get('HEAP_SIZE') is not None:
                        c2000_linker_opt_dict['HEAP_SIZE'] = (tool_options.get('HEAP_SIZE') or "0x400")
                    for k, v in c2000_linker_opt_dict.items():
                        if v is True:
                            c2000_linker_opt_lines.append("--{0}".format(k.lower()))
                        else:
                            c2000_linker_opt_lines.append("--{0}={1}".format(k.lower(), str(v).lower()))
                    # end of for loop
                # end of for loop
                if len(c2000_linker_opt_lines) > 0:
                    outfile.write('\nset(CMAKE_C2000_LINKER_STACK_SIZE_HEAP_SIZE_FLAGS "{0}" CACHE STRING "")'.format(' '.join(c2000_linker_opt_lines)))

                outfile.write('\n')
                outfile.write(f'set(CG_TOOL_ROOT_HINT "C:/ti/ccsv7/tools/compiler/ti-cgt-c2000_{OPT_CODEGEN_VERSION}")\n')
                # outfile.write('set(TI_CGT_C2000_DIR ${CG_TOOL_ROOT} CACHE STRING "")\n')

        outfile.write('\n')
        outfile.write(f'project({current_target_name} C CXX ASM)\n')
        outfile.write('\n')
        outfile.write(f'set(PROJECT_DIR ${{CMAKE_CURRENT_LIST_DIR}}/{quote_path(self.cdt_prj.PROJECT_DIR)})\n')
        # outfile.write('\n')
        # outfile.write("if(CMAKE_TOOLCHAIN_FILE)\n")
        # outfile.write("\tinclude(${CMAKE_TOOLCHAIN_FILE})\n")
        # outfile.write("endif(CMAKE_TOOLCHAIN_FILE)\n")

        SRC_FILES = self.get_src_files(config, current_target_name)
        LIB_FILES = self.get_lib_files(config, current_target_name)

        if SRC_FILES is not None and len(SRC_FILES) > 0:
            outfile.write(f'\nadd_executable({current_target_name}')
            for src_file in SRC_FILES:
                src_file = norm_path(self.expand_variable(src_file))
                src_file = self.path_from_file_item(src_file)
                outfile.write(f"\n\t{src_file}")
            outfile.write('\n)\n')

            for tool_id, tool_options in config_info.COMPILER_OPTIONS.items():
                outstrlist = []
                for item in (tool_options.get('symbols_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"{item_str}")
                for item in (tool_options.get('DEFINE_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = self.expand_variable(item_val)
                    outstrlist.append(f"{item_str}")
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_compile_definitions({current_target_name} PUBLIC\n\t")
                    outfile.write('\n\t'.join(outstrlist))
                    outfile.write('\n)\n')

                outstrlist = []
                for item in (tool_options.get('paths_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = norm_path(self.expand_variable(item_val))
                    outstrlist.append(self.path_from_dir_item(item_str))
                for item in (tool_options.get('INCLUDE_PATH_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = norm_path(self.expand_variable(item_val))
                    outstrlist.append(self.path_from_dir_item(item_str))
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_include_directories({current_target_name} PUBLIC\n\t")
                    outfile.write('\n\t'.join(outstrlist))
                    outfile.write('\n)\n')

            for tool_id, tool_options in config_info.LINKER_OPTIONS.items():
                outstrlist = []
                for item in (tool_options.get('paths_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = norm_path(self.expand_variable(item_val))
                    outstrlist.append(self.path_from_dir_item(item_str))
                for item in (tool_options.get('SEARCH_PATH_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = norm_path(self.expand_variable(item_val))
                    outstrlist.append(self.path_from_dir_item(item_str))
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_link_directories({current_target_name} PUBLIC\n\t")
                    outfile.write('\n\t'.join(outstrlist))
                    outfile.write('\n)\n')

                outstrlist = []
                for item in (tool_options.get('input_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = norm_path(self.expand_variable(item_val))
                    outstrlist.append(self.path_from_file_item(item_str))
                for item in (tool_options.get('LIBRARY_SUBITEMS') or []):
                    item_val = item['value']
                    item_str = norm_path(self.expand_variable(item_val))
                    outstrlist.append(self.path_from_file_item(item_str))
                for item in LIB_FILES:
                    item_str = norm_path(self.expand_variable(item))
                    outstrlist.append(self.path_from_file_item(item_str))
                # process exclude list
                for exclude_info in config_info.EXCLUDE_INFO:
                    for exclude_item in exclude_info['exclude_item_list']:
                        if len(exclude_item) > 0:
                            outstrlist = list(filter(lambda x: not x.endswith(exclude_item), outstrlist))
                if 'C2000' in config_info.TARGETPLATFORM.get('superClass'):
                    libc_found = False
                    for item in outstrlist:
                        if "libc.a" in item:
                            libc_found = True
                            break
                    if libc_found:
                        outstrlist = list(filter(lambda item: "libc.a" not in item, outstrlist))
                        outstrlist.append("--library=libc.a # HACK: (TI-Compiler) This is a way to attempt searching for libc.a in the library path.")
                if len(outstrlist) > 0:
                    outfile.write(f"\ntarget_link_libraries({current_target_name} PUBLIC\n\t")
                    outfile.write('\n\t'.join(outstrlist))
                    outfile.write('\n)\n')

            for file_resource_path, file_options in config_info.FILEINFO.items():
                # print(file_resource_path, file_options)
                outstrlist = []
                file_path = self.cdt_prj.RESOURCE_MAP.get(file_resource_path)
                if file_path is None:
                    continue
                tool_options = file_options.get('COMPILER_OPTIONS') or {}
                for file_tool_id, file_tool_options in tool_options.items():
                    # print(file_tool_options)
                    for item in (file_tool_options.get('symbols_SUBITEMS') or []):
                        item_val = item['value']
                        item_str = self.expand_variable(item_val)
                        outstrlist.append(f"{item_str}")
                    for item in (file_tool_options.get('DEFINE_SUBITEMS') or []):
                        item_val = item['value']
                        item_str = self.expand_variable(item_val)
                        outstrlist.append(f"{item_str}")
                if len(outstrlist) > 0:
                    outfile.write(f"\nset_source_files_properties({file_path} PROPERTIES COMPILE_DEFINITIONS\n")
                    outfile.write('\t"')
                    outfile.write(';'.join(outstrlist).replace('"', '\\"'))
                    outfile.write('"\n)\n')

            if 'C2000' in config_info.TARGETPLATFORM.get('superClass'):
                outfile.write('\n')
                outfile.write('set(CMAKE_LIBRARY_PATH_FLAG "--search_path=")\n')
                outfile.write('set(CMAKE_LINK_LIBRARY_FLAG "--library=")\n')
                outfile.write('\n')
                outfile.write("if (COMMAND mark_as_target_executable)\n")
                outfile.write(f"\tmark_as_target_executable({current_target_name})\n")
                outfile.write("endif(COMMAND mark_as_target_executable)\n")

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
        generator = cmake_generator(cdt_prj)
        generator.generate(config_name, outfile)
        break


if __name__ == "__main__":
    main()
