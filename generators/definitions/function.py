from collections import defaultdict, OrderedDict
from itertools import product

from CppHeaderParser import CppMethod
from inflection import camelize

from generators.config import INDENT, FUNCTIONS_TO_SKIP, OVERLOADED_TEMPLATED_FUNCTIONS_TO_INCLUDE
from generators.definitions.method import Method
from generators.definitions.method import filter_template_types, template_types_generator
from generators.point_types_utils import filter_types
from generators.utils import function_definition_name


def filter_functions(cppfunctions, header_name):
    filtered = []
    by_name = defaultdict(list)
    for f in cppfunctions:
        by_name[f["name"]].append(f)

    for f in cppfunctions:
        if "<" in f["name"] or ">" in f["name"]:
            continue
        if (header_name, f["name"]) in FUNCTIONS_TO_SKIP:
            continue
        if "::" in f["rtnType"].replace(" ", ""):  # bug in CppHeaderParser for methods defined outside class
            continue
        if f["template"] and f["template"].replace(" ", "") == "template<>":  # skip specialized templated functions
            continue
        other_templated_with_same_name = any(other["template"] and other["template"].replace(" ", "")
                                             for other in by_name[f["name"]]
                                             if not other == f)
        if other_templated_with_same_name:
            if f['name'] in OVERLOADED_TEMPLATED_FUNCTIONS_TO_INCLUDE:
                print('Adding overload for templated function {}'.format(f['name']))
            else:
                continue
        filtered.append(f)
    return filtered


def get_methods_defined_outside(cppfunctions):
    filtered = []
    for f in cppfunctions:
        if "::" in f["rtnType"].replace(" ", ""):  # bug in CppHeaderParser for methods defined outside class
            filtered.append(f)
    return filtered


def generate_function_definitions(cppfunctions,
                                  module_name,
                                  header_name,
                                  indent="",
                                  not_every_point_type=False):
    cppfunctions = filter_functions(cppfunctions, header_name)
    cppfunctions = list(sorted(cppfunctions, key=lambda x: x["name"]))
    functions = [Method(f, is_an_overload=True) for f in cppfunctions]
    s = []
    a = s.append
    i = INDENT

    # group functions by template types
    templated_functions_grouped = defaultdict(list)
    for f in functions:
        template = f.cppmethod["template"]
        if template:
            template = template.replace("\n", "")
            pos = template.find("<")
            template_types = filter_template_types(template[pos + 1:-1], keep=["typename", "class"])
            all_templated_types = filter_template_types(template[pos + 1:-1], keep_all=True)
            f.templated_types = OrderedDict(((t, [t]) for t in all_templated_types))
            templated_functions_grouped[template_types].append(f)
        else:
            templated_functions_grouped[tuple()].append(f)

    templated_functions_grouped = OrderedDict(sorted(templated_functions_grouped.items()))

    for n, (type_names, group) in enumerate(templated_functions_grouped.items(), 1):
        if type_names:
            a(group[0].cppmethod.get("template"))
        a("{ind}void define{sub}{name}Functions%s(py::module &m) {ob}" % n)
        for f in group:
            function_prefix = f.cppmethod["namespace"]
            function_prefix = function_prefix[:-2] if function_prefix.endswith("::") else function_prefix
            value = f.to_str(function_prefix, "m")
            if f.templated_types:
                value = value[0]
            a("{ind}{i}%s;" % value)
        a("{cb}")
        a("")

    a("{ind}void define{sub}{name}Functions(py::module &m) {ob}")
    for n, (type_names, group) in enumerate(templated_functions_grouped.items(), 1):
        if type_names:
            types = [t[1] for t in template_types_generator(type_names, header_name, group[0].cppmethod["name"])]
            if isinstance(types[0], str):
                all_types = filter_types(types) if not_every_point_type else types
            elif isinstance(types[0], list):
                if not_every_point_type:
                    types = list(map(filter_types, types))
                all_types = list(product(*types))
            else:
                raise NotImplementedError
            for t in all_types:
                a("{ind}{i}define{sub}{name}Functions%s<%s>(m);" % (n, ", ".join(t)))
        else:
            a("{ind}{i}define{sub}{name}Functions%s(m);" % (n,))

    a("{ind}{cb}")
    a("")

    data = {
        "ind": indent,
        "i": i,
        "name": function_definition_name(header_name),
        "sub": camelize(module_name),
        "ob": "{",
        "cb": "}"
    }
    return "\n".join([line.format(**data) for line in s])
