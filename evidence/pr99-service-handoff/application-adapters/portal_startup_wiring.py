"""Bind the hash-pinned original portal builder during exclusive startup only.

The original controller supplies the verified repository/store binding. This
does not open databases, create authority, install services, or claim a Writer.
"""
import ast
import hashlib
from credential_key_binding import CredentialBindingHold

PORTAL_SHA = '57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1'


def compile_wired_builder(source, original_globals, bind_store):
    if hashlib.sha256(source).hexdigest() != PORTAL_SHA:
        raise CredentialBindingHold('PORTAL_SOURCE_CHANGED')
    if not callable(bind_store) or '_pr99_bind_store' in original_globals:
        raise CredentialBindingHold('EXPLICIT_ORIGINAL_STORE_BINDING_REQUIRED')
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_service')
    replacements = [0, 0]
    class Wiring(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == 'CredentialStore':
                if (node.args or len(node.keywords) != 1 or node.keywords[0].arg != 'repository'
                        or not isinstance(node.keywords[0].value, ast.Name)
                        or node.keywords[0].value.id != 'credential_repository'):
                    raise CredentialBindingHold('NATIVE_STORE_CALL_CHANGED')
                replacements[0] += 1
                return ast.copy_location(ast.Call(func=ast.Name(id='_pr99_bind_store', ctx=ast.Load()),
                    args=[node.keywords[0].value, ast.Name(id='CredentialStore', ctx=ast.Load())], keywords=[]), node)
            return node

        def visit_ExceptHandler(self, node):
            if (isinstance(node.type, ast.Name) and node.type.id == 'Exception'
                    and len(node.body) == 1 and isinstance(node.body[0], ast.Assign)
                    and len(node.body[0].targets) == 1
                    and isinstance(node.body[0].targets[0], ast.Name)
                    and node.body[0].targets[0].id == 'credential_intake'
                    and isinstance(node.body[0].value, ast.Constant)
                    and node.body[0].value.value is None):
                replacements[1] += 1
                node.body = [ast.Raise(exc=ast.Call(func=ast.Name(id='_pr99_hold', ctx=ast.Load()),
                             args=[ast.Constant(value='CREDENTIAL_INTAKE_STARTUP_FAILED')], keywords=[]),
                             cause=ast.Constant(value=None))]
            return node
    function = Wiring().visit(function)
    if replacements != [1, 1]:
        raise CredentialBindingHold('PORTAL_STARTUP_SHAPE_CHANGED')
    namespace = dict(original_globals)
    namespace.update(_pr99_bind_store=bind_store, _pr99_hold=CredentialBindingHold)
    # Only the selected function definition executes, never module-level code.
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                 '<PR99-wired-original-portal-builder>', 'exec'), namespace)
    return namespace['build_service']


def install_startup_binding(module, source, bind_store, verify_exclusive_startup):
    """Replace only build_service, before serve creates HTTP/background threads.

    bind_store receives the ACTUAL repository and original native Store class.
    It must return the fully bound store facade from the original controller.
    Missing original controller/operation identity is HOLD, never inferred here.
    """
    if (not callable(verify_exclusive_startup)
            or verify_exclusive_startup(module) is not True
            or getattr(module, '_pr99_builder_bound', False)):
        raise CredentialBindingHold('EXCLUSIVE_ORIGINAL_STARTUP_REQUIRED')
    original = module.build_service
    wired = compile_wired_builder(source, vars(module), bind_store)
    def build(state_root):
        if verify_exclusive_startup(module) is not True:
            raise CredentialBindingHold('STARTUP_BINDING_WITHDRAWN')
        service = wired(state_root)
        if getattr(service, 'credential_intake', None) is None:
            raise CredentialBindingHold('CREDENTIAL_INTAKE_NOT_WIRED')
        return service
    if module.build_service is not original:
        raise CredentialBindingHold('BUILDER_CHANGED_DURING_BINDING')
    module.build_service = build
    module._pr99_builder_bound = True
