#!/usr/bin/env python3
"""Offline AST import closure over exact SHA-bound inputs; executes no candidates.

Walks function bodies as well as top-level imports. Literal dynamic imports are
checked. Nonliteral imports and direct source loaders are reported for explicit
review; this is static dependency evidence, never an execution-safety proof.
"""
import argparse
import ast
import json
import math
import os
import sys
import sysconfig

from build_epoch7_kit import validate_input
from epoch7_recovery_entry import DescriptorTree, decode, need, sha


def standard_roots():
    result = set(sys.builtin_module_names)
    # Source-build interpreters (the checked local CPython 3.6) may have a
    # nonexistent configured install prefix. Use the executing stdlib modules,
    # never the source tree being audited, to locate that interpreter's files.
    roots = {sysconfig.get_path('stdlib'), os.path.dirname(os.__file__)}
    if getattr(math, '__file__', None): roots.add(os.path.dirname(math.__file__))
    for root in tuple(roots): roots.add(os.path.join(root, 'lib-dynload'))
    for root in sorted(roots):
        if not os.path.isdir(root): continue
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if name.endswith('.py'): result.add(name[:-3])
            elif name.endswith(('.so', '.pyd')): result.add(name.split('.')[0])
            elif os.path.isfile(os.path.join(path, '__init__.py')): result.add(name)
    return result


def references(raw, filename):
    tree = ast.parse(raw, filename=filename)
    imports, dynamic = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno, 'import') for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((('.' * node.level) + (node.module or ''), node.lineno, 'from'))
        elif isinstance(node, ast.Call):
            function = node.func
            name = function.id if isinstance(function, ast.Name) else (
                function.attr if isinstance(function, ast.Attribute) else '')
            if name in ('__import__', 'import_module'):
                argument = node.args[0] if node.args else None
                if hasattr(ast, 'Constant') and isinstance(argument, ast.Constant) and type(argument.value) is str:
                    imports.append((argument.value, node.lineno, name))
                elif sys.version_info < (3, 8) and isinstance(argument, ast.Str):
                    imports.append((argument.s, node.lineno, name))
                else: dynamic.append({'line': node.lineno, 'kind': 'NONLITERAL_' + name})
            elif name in ('spec_from_file_location', 'exec_module', 'exec', 'eval'):
                dynamic.append({'line': node.lineno, 'kind': name})
    return imports, dynamic


def analyze(cache, modules, suites, standard):
    records, missing, dynamic = [], [], []
    contexts = [('modules', True, modules, list(modules.values()))]
    covered = set(modules.values()) | {path for row in suites.values() for path in row['imports'].values()}
    scripts = sorted(path for path in cache if path.endswith('.py') and path not in covered)
    contexts.append(('bootstrap_scripts', True, modules, scripts))
    contexts.extend((name, row['enabled'], dict(modules, **row['imports']), list(row['imports'].values()))
                    for name, row in sorted(suites.items()))
    for scope, required, available, paths in contexts:
        for path in sorted(set(paths)):
            imports, loaders = references(cache[path], path)
            for name, line, kind in imports:
                category = 'candidate' if name in available else (
                    'stdlib' if name.split('.')[0] in standard and not name.startswith('.') else 'MISSING')
                row = {'scope': scope, 'required': required, 'path': path, 'line': line,
                       'name': name, 'kind': kind, 'resolution': category}
                records.append(row)
                if category == 'MISSING': missing.append(row)
            dynamic.extend(dict(row, scope=scope, required=required, path=path) for row in loaders)
    return {'kind': 'STATIC_IMPORT_CLOSURE_ONLY', 'candidate_execution': 'NOT_RUN',
            'success': not any(row['required'] for row in missing),
            'source_sha256': {path: sha(raw) for path, raw in sorted(cache.items()) if path.endswith('.py')},
            'references': records, 'missing': missing, 'source_loading_review': dynamic,
            'limits': 'Nonliteral import names and direct exec/file-loader sites require independent review.'}


def audit(source_root, value):
    validate_input(value)
    owners = tuple(sorted(set(((0, 0), (os.geteuid(), os.getegid())))))
    cache = {}
    with DescriptorTree(source_root, owners) as source:
        for target, row in sorted(value['files'].items()):
            if target.endswith('.py'):
                raw = source.read(row['source']); need(sha(raw) == row['sha256'], 'SOURCE_CHANGED')
                cache[target] = raw
        source.recheck()
    result = analyze(cache, value['modules'], value['test_suites'], standard_roots())
    result.update(runtime_source_commit=value['runtime_source_commit'],
                  runtime_source_tree=value['runtime_source_tree'],
                  kit_source_commit=value['kit_source_commit'], kit_source_tree=value['kit_source_tree'])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--input-map', required=True)
    args = parser.parse_args(argv)
    path = os.path.abspath(args.input_map)
    owners = tuple(sorted(set(((0, 0), (os.geteuid(), os.getegid())))))
    with DescriptorTree(os.path.dirname(path), owners) as tree:
        raw = tree.read(os.path.basename(path)); tree.recheck()
    result = audit(os.path.abspath(args.source_root), decode(raw))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['success'] else 1


if __name__ == '__main__': sys.exit(main())
