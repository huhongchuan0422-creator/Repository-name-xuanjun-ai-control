"""Read-only PR99 source inventory, including Python -m service entries.

This is discovery evidence, NOT writer-fence or drain proof. Never emits argv,
environment values, source bodies, database rows, or secret contents.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re

SOURCE = 'iZ6wee8q9z4t03hvqumwfhZ'
MARKERS = {'SessionLocal', 'create_db_engine', 'CredentialRepository',
           'CredentialStore', 'save_credential', 'load_credential',
           'create_engine', 'sqlite3', 'connect', 'commit', 'execute'}


def beneath(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def python_entry(argv, cwd, root):
    """Resolve explicit scripts and -m entries without executing either."""
    if not argv or not re.search(r'python(?:[0-9.]+)?$', Path(argv[0]).name):
        return None
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == '-m':
            if index + 1 >= len(argv):
                return None
            name = argv[index + 1]
            if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', name):
                return None
            candidate = root.joinpath(*name.split('.'))
            module = candidate.with_suffix('.py')
            package = candidate / '__main__.py'
            return module if module.is_file() else package if package.is_file() else None
        if arg in ('-c', '-', '--'):
            return None
        if arg in ('-W', '-X'):
            index += 2
            continue
        if arg.startswith('-'):
            index += 1
            continue
        path = Path(arg)
        path = path if path.is_absolute() else cwd / path
        return path if beneath(path, root) and path.suffix == '.py' else None
    return None


def read_code(path, root):
    if not beneath(path, root) or any(p.is_symlink() for p in [path, *path.parents]):
        raise RuntimeError('UNSAFE_CODE_PATH')
    with path.open('rb') as stream:
        raw = stream.read(2000001)
    if len(raw) > 2000000:
        raise RuntimeError('CODE_SIZE_LIMIT')
    return raw


def module_candidates(name, root):
    parts = name.split('.') if name else []
    if not parts or any(not re.fullmatch(r'[A-Za-z_]\w*', p) for p in parts):
        return []
    result = []
    for end in range(1, len(parts) + 1):
        init = root.joinpath(*parts[:end], '__init__.py')
        if init.is_file():
            result.append(init)
    module = root.joinpath(*parts).with_suffix('.py')
    if module.is_file():
        result.append(module)
    return result


def inspect_graph(entry, root):
    pending = [entry]
    for parent in entry.relative_to(root).parents:
        if str(parent) != '.':
            init = root / parent / '__init__.py'
            if init.is_file():
                pending.append(init)
    modules = {}
    while pending:
        path = pending.pop()
        rel = path.relative_to(root).as_posix()
        if rel in modules:
            continue
        if len(modules) >= 2000:
            raise RuntimeError('MODULE_GRAPH_LIMIT')
        raw = read_code(path, root)
        tree = ast.parse(raw, filename=rel)
        package = list(path.relative_to(root).parts[:-1])
        imports = set()
        dynamic = []
        markers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package)-node.level+1] if node.level else []
                if node.level > len(package):
                    raise RuntimeError('RELATIVE_IMPORT_OUTSIDE_ROOT')
                name = '.'.join(prefix + ([node.module] if node.module else []))
                if name:
                    imports.add(name)
                for alias in node.names:
                    if alias.name != '*':
                        imports.add('.'.join(filter(None, (name, alias.name))))
            elif isinstance(node, ast.Call):
                function = node.func
                name = function.id if isinstance(function, ast.Name) else function.attr if isinstance(function, ast.Attribute) else ''
                if name in MARKERS:
                    markers.add(name)
                if name in ('__import__', 'import_module'):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and not node.args[0].value.startswith('.'):
                        imports.add(node.args[0].value)
                    else:
                        dynamic.append(node.lineno)
            elif isinstance(node, ast.Name) and node.id in MARKERS:
                markers.add(node.id)
        modules[rel] = {'sha256': hashlib.sha256(raw).hexdigest(),
                        'database_markers': sorted(markers),
                        'unresolved_dynamic_import_lines': sorted(dynamic)}
        for name in imports:
            pending.extend(module_candidates(name, root))
    return modules


def collect(root=Path('/opt/trading-system'), proc=Path('/proc')):
    entries = {}
    failures = []
    unresolved = []
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            cwd = Path(os.readlink(process / 'cwd'))
            argv = [part.decode('utf-8', 'strict') for part in
                    (process / 'cmdline').read_bytes().split(b'\0') if part]
            relevant = beneath(cwd, root) or any(str(root) in arg for arg in argv)
            if not relevant:
                continue
            entry = python_entry(argv, cwd, root)
            group = (process / 'cgroup').read_text()
            units = sorted(set(re.findall(r'([A-Za-z0-9_.@-]+\.service)(?:/|$)', group, re.M)))
            if entry is None:
                unresolved.append({'pid': int(process.name), 'units': units,
                                   'reason': 'ENTRY_NOT_RESOLVED'})
                continue
            rel = entry.relative_to(root).as_posix()
            row = entries.setdefault(rel, {'pids': [], 'units': set()})
            row['pids'].append(int(process.name))
            row['units'].update(units)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (PermissionError, UnicodeError, ValueError):
            failures.append(int(process.name))
    report = {'source_host': SOURCE, 'class': 'READ_ONLY_DISCOVERY_NOT_FENCE',
              'entries': [], 'unresolved_processes': unresolved,
              'scan_failures': failures, 'writer_coverage': 'NOT_PROVEN',
              'source_services_stopped': False, 'production_cutover': False}
    for rel, row in sorted(entries.items()):
        modules = inspect_graph(root / rel, root)
        report['entries'].append({'entry': rel, 'pids': sorted(row['pids']),
                                 'units': sorted(row['units']),
                                 'static_module_count': len(modules),
                                 'dependencies': {name: evidence for name, evidence in sorted(modules.items())
                                     if evidence['database_markers'] or evidence['unresolved_dynamic_import_lines']}})
    return report


if __name__ == '__main__':
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != SOURCE:
        raise SystemExit('HOLD_HOST_OR_IDENTITY')
    print(json.dumps(collect(), sort_keys=True, indent=2))
