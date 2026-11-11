"""Composition for the existing authenticated Owner controller; no server."""
import copy
from foundation_integration import validate_binding
from owner_foundation_reader import read_authorized_owner_foundations


class OwnerFoundationController:
    """Trusted controller config owns context supplier and session authorizer.

    Supplier returns the EXISTING protected connection transaction context and
    exact reader arguments. Client requests cannot supply DBs or validators.
    Authorizer must use a real authenticated session and fixed Owner identity;
    this composition does not create or authenticate that session.
    """
    def __init__(self, context_supplier, owner_authorizer):
        if not callable(context_supplier) or not callable(owner_authorizer):
            raise ValueError('TRUSTED_CONTROLLER_DEPENDENCIES_REQUIRED')
        self._context_supplier = context_supplier
        self._owner_authorizer = owner_authorizer

    def read(self, task_id):
        if not isinstance(task_id, str) or not 1 <= len(task_id) <= 200:
            raise ValueError('INVALID_OWNER_TASK_REQUEST')
        # The protected supplier, not request JSON, selects transaction/source.
        with self._context_supplier(task_id) as arguments:
            if not isinstance(arguments, dict):
                raise ValueError('INVALID_CONTROLLER_READ_CONTEXT')
            binding = copy.deepcopy(arguments.get('binding'))
            validate_binding(binding)
            if binding['task_id'] != task_id:
                raise ValueError('CONTROLLER_TASK_BINDING_MISMATCH')
            values = dict(arguments)
            values['binding'] = binding
            return read_authorized_owner_foundations(self._owner_authorizer, **values)
