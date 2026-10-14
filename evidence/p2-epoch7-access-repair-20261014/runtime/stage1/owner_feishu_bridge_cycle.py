"""Credential-owner bridge orchestration; canonical state stays at ledger server."""
import re
from owner_feishu_transport import OwnerFeishuTransport
from owner_feishu_history import OwnerFeishuHistory


def run_cycle(canonical, api, binding):
    # binding is a protected root-owned receiver/package record, never RPC params.
    if (not isinstance(binding,dict) or set(binding)!={'chat_id','app_id','package_sha256'} or
            not isinstance(binding['app_id'],str) or re.fullmatch(r'cli_[A-Za-z0-9_-]{1,128}',binding['app_id']) is None):
        raise ValueError('PROTECTED_OWNER_BINDING_REQUIRED')
    # Constructor validates destination/hash before credentials or claim acquisition.
    transport = OwnerFeishuTransport(binding['chat_id'],binding['package_sha256'],api,
        lambda claim:canonical({'operation':'guard','claim':claim}) is True)
    api.verify_private_owner(binding)
    work = canonical({'operation':'begin'})
    if not isinstance(work,dict) or work.get('mode') not in ('IDLE','HELD','SEND','RECONCILE'):
        raise ValueError('CANONICAL_DELIVERY_UNCONFIRMED')
    if work['mode'] in ('IDLE','HELD'):
        return {'state':work['mode'],'model_calls':0,'receiver_ack':False}
    claim = work.get('claim')
    if not isinstance(claim,dict) or claim.get('package_sha256')!=binding['package_sha256']:
        raise ValueError('ACTIVE_PACKAGE_MISMATCH')
    identity, kind = claim.get('event_key'),claim.get('event_kind')
    receipt = None
    status = 'UNCERTAIN' if work['mode']=='SEND' else 'UNKNOWN'
    try:
        if work['mode']=='SEND':
            receipt = transport('OWNER',identity,kind,{},claim)
        else:
            history = OwnerFeishuHistory(api.get,binding['chat_id'],binding['app_id'])
            observed = transport.reconcile(identity,kind,history,claim)
            if observed!='UNKNOWN':receipt=observed
        if receipt is not None:status='ACK'
    except Exception:
        # No external exception strings or blind send retries cross this boundary.
        receipt = None
    result = canonical({'operation':'finish','claim':claim,'status':status,'receipt_id':receipt})
    if (not isinstance(result,dict) or result.get('state') not in ('ACKED','HELD','SENDING_UNCERTAIN') or
            result.get('receiver_ack') is not (result['state']=='ACKED') or type(result.get('model_calls')) is not int or result.get('model_calls')!=0):
        raise ValueError('CANONICAL_ACK_UNCONFIRMED')
    return result
