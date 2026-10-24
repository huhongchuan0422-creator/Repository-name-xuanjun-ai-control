"""Bounded static storage dataflow. No business import, environment or file I/O.

Resolved paths describe SOURCE expressions, never effective configuration or
permission to migrate. Unsupported/conditional assignments remain unresolved.
"""
import ast
import re
from pathlib import PurePosixPath

MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
RUNTIME = re.compile(r"/opt/trading-system/runtime/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+")
STORAGE = re.compile(r"Store|Repository|Ledger|State")


def module_candidates(module):
    if not isinstance(module, str) or not MODULE.fullmatch(module):
        raise ValueError('MODULE_NAME_REJECTED')
    stem = module.replace('.', '/')
    return (stem + '.py', stem + '/__init__.py')


def runtime_path(value):
    if not isinstance(value, (str, PurePosixPath)):
        return None
    value = str(value)
    if len(value) > 400 or not RUNTIME.fullmatch(value) or any(p in ('.', '..') for p in value.split('/')):
        return None
    return value


def imports(tree, filename):
    """Include function-local and package-relative imports without importing them."""
    result = {}
    package = filename.removesuffix('/__init__.py').replace('/', '.') if filename.endswith('/__init__.py') else filename.rsplit('/', 1)[0].replace('/', '.')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ''
            if node.level:
                parts = package.split('.')
                if node.level > len(parts):
                    continue
                prefix = '.'.join(parts[:len(parts)-node.level+1] + ([prefix] if prefix else []))
            for alias in node.names:
                if alias.name != '*' and prefix:
                    result[alias.asname or alias.name] = prefix + '.' + alias.name
    return result


def analyze_source(raw, filename, Defaults, shape):
    # Use the existing expression interpreter, with ALL environment reads unknown.
    # The legacy TRADING_DATABASE_URL absent-default assumption is not inherited.
    class StrictDefaults(Defaults):
        def value(self, node, scope):
            if isinstance(node, ast.Call) and self.fullname(node.func) in ('os.getenv', 'os.environ.get'):
                raise ValueError('ENVIRONMENT_NOT_SOURCE_DEFAULT')
            if isinstance(node, ast.Call) and self.fullname(node.func) == 'pathlib.Path' and len(node.args) == 1 and not node.keywords:
                value = self.value(node.args[0], scope)
                if isinstance(value, PurePosixPath):
                    return value
            if isinstance(node, ast.IfExp):
                condition = self.value(node.test, scope)
                if type(condition) not in (str,int,bool,type(None)) and not isinstance(condition,PurePosixPath):
                    raise ValueError('CONDITIONAL_UNKNOWN')
                return self.value(node.body if condition else node.orelse, scope)
            return super().value(node, scope)

    engine = StrictDefaults(raw, '/opt/trading-system/' + filename, '/opt/trading-system')
    engine.imports = imports(engine.tree, filename)
    constructors, assignments, operations, options = [], [], [], []
    paths = set()

    def expression(node, scope):
        result = {'shape': shape(node), 'source_runtime_path': None}
        try:
            result['source_runtime_path'] = runtime_path(engine.value(node, scope))
        except Exception:
            # The supplied interpreter uses its own Unresolved type. No source is
            # executed; all failures are conservatively unresolved, not fallback.
            pass
        if result['source_runtime_path']:
            paths.add(result['source_runtime_path'])
        return result

    def walk(statements, scope, owner):
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local = dict(engine.globals)
                engine.defaults(statement, local)
                if statement.name == '__init__' and statement.args.args and statement.args.args[0].arg == 'self':
                    local['self'] = {}
                walk(statement.body, local, owner + '.' + statement.name)
                continue
            if isinstance(statement, ast.ClassDef):
                walk(statement.body, dict(engine.globals), statement.name)
                continue
            if isinstance(statement, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)):
                # Record unresolved shapes in conditional blocks, never merge a
                # branch's assignment into the enclosing execution flow.
                for child in ast.iter_child_nodes(statement):
                    if isinstance(child, ast.stmt):
                        unknown = {key: object() for key in scope}
                        walk([child], unknown, owner)
                # Do not retain an earlier known value after unsupported control
                # flow could have changed it. Unknown is never Python None.
                for child in ast.walk(statement):
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                        scope[child.id] = object()
                    if isinstance(child,ast.Attribute) and isinstance(child.ctx,ast.Store) and isinstance(child.value,ast.Name) and child.value.id=='self' and isinstance(scope.get('self'),dict):
                        scope['self'][child.attr] = object()
                continue
            engine.assign(statement, scope)
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                for target in targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self' and re.search(r'path|root|file|dir|db', target.attr, re.I):
                        assignments.append({'owner': owner, 'line': statement.lineno, 'attribute': target.attr, 'value': expression(statement.value, scope)})
                        if isinstance(scope.get('self'),dict):
                            try:
                                scope['self'][target.attr] = engine.value(statement.value,scope)
                            except Exception:
                                scope['self'][target.attr] = object()
            for node in ast.walk(statement):
                if not isinstance(node, ast.Call):
                    continue
                name = engine.fullname(node.func)
                if STORAGE.search(name) and MODULE.fullmatch(name):
                    constructors.append({'owner': owner, 'line': node.lineno, 'name': name,
                        'arguments': [expression(a, scope) for a in node.args[:6]],
                        'keywords': [{'name': kw.arg or 'EXPANSION_UNRESOLVED', 'value': expression(kw.value, scope)} for kw in node.keywords[:12]]})
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument':
                    option = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
                    if isinstance(option, str) and re.fullmatch(r'--[a-z][a-z-]{0,50}', option):
                        for kw in node.keywords:
                            if kw.arg == 'default':
                                options.append({'line': node.lineno, 'option': option, 'default': expression(kw.value, scope)})
                if name and (name.startswith(('sqlite3.', 'json.')) or name.rsplit('.', 1)[-1] in ('open', 'write_text', 'write_bytes', 'read_text', 'read_bytes', 'replace', 'unlink', 'mkdir')):
                    operations.append({'owner': owner, 'line': node.lineno, 'name': name, 'arguments': [expression(a, scope) for a in node.args[:3]]})
    walk(engine.tree.body, dict(engine.globals), 'MODULE')
    result = {'imports': engine.imports, 'constructors': constructors[:30], 'path_assignments': assignments[:40], 'storage_operations': operations[:60], 'cli_defaults': options[:30], 'source_paths': sorted(paths), 'omitted': max(0, len(constructors)-30)+max(0, len(assignments)-40)+max(0, len(operations)-60)+max(0, len(options)-30)}
    return result
