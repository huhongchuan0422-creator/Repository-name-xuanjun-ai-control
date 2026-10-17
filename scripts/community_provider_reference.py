"""One deterministic provider order reference for original scoped orders."""
import hashlib
import re
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import scope,valid_id


def provider_order_reference(sp_mchid,identity,reference):
    scope(identity)
    if type(sp_mchid) is not str or not re.fullmatch('[0-9]{6,32}',sp_mchid) or not valid_id(reference):
        raise ValueError('INVALID_PROVIDER_ORDER_REFERENCE')
    return 'cm'+hashlib.sha256(canonical(dict(sp_mchid=sp_mchid,scope=identity,reference=reference))).hexdigest()[:30]
