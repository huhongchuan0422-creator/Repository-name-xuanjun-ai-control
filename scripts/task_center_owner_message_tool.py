"""Bind the original owner-alert host seam to an injected message tool.

Only the hosting runtime can supply the real messaging callable and trusted
scope/binding resolvers. This module neither accesses OpenClaw RPC nor grants
permissions, and does not install itself in a server or job.
"""
from task_center_owner_alert_adapter import OwnerAlertAdapter


def parse_message_result(raw, expected_target=None):
    """Map observed Feishu send results conservatively; SENT never means ACK.

    A successful call, sentAt or a source-reply flag alone does not prove the
    target platform send has settled. Ambiguity, including inconsistent IDs,
    is UNKNOWN. No exact-attempt no-effect query is implied by this parser.
    """
    if not isinstance(raw,dict) or raw.get('ok') is not True or raw.get('channel')!='feishu' or raw.get('action')!='send':return None
    delivery=raw.get('messageDelivery')
    if not isinstance(delivery,dict) or delivery.get('status')!='settled':return None
    # Optional observed fields are evidence only when present; never invent
    # destination proof. An explicit mismatch cannot become SENT.
    if 'chatId' in raw:
        if expected_target is None or raw['chatId']!=(expected_target[5:] if expected_target.startswith('user:') else expected_target):return None
    if 'deliveredTargets' in delivery:
        targets=delivery['deliveredTargets']
        if expected_target is None or not isinstance(targets,list) or not targets or any(x!=(expected_target[5:] if expected_target.startswith('user:') else expected_target) for x in targets):return None
    receipt=raw.get('receipt')
    receipt_id=receipt.get('primaryPlatformMessageId') if isinstance(receipt,dict) else None
    message_id=raw.get('messageId')
    if message_id is not None and receipt_id is not None and message_id!=receipt_id:return None
    identifier=message_id if message_id is not None else receipt_id
    if not isinstance(identifier,str) or not identifier or identifier!=identifier.strip() or len(identifier)>256:return None
    return {'state':'SENT','settled':True,'message_id':identifier}


def make_owner_message_adapter(owner_destination, authorize_task, resolve_binding, message_tool, message_mode=None):
    """The host injects the existing functions.message capability, not an RPC.

    ``message_tool`` must be a host callable for the actual main tool. The
    current platform interface does not provide an idempotency key or exact
    attempt lookup; local original outbox intent still prevents blind retries.
    """
    if not isinstance(owner_destination,str) or not owner_destination.startswith('user:') or len(owner_destination)<=5:
        raise ValueError('OWNER_DIRECT_DESTINATION_REQUIRED')
    if not callable(message_tool):raise ValueError('HOST_MESSAGE_TOOL_REQUIRED')
    # Mode is a trusted host registration fact, never a request-body field.
    # Do not probe by invoking a callback or guess from Python function type.
    if message_mode not in ('sync','async'):raise ValueError('HOST_MESSAGE_MODE_REQUIRED')
    def invoke(destination,text,outbox_id,delivery_attempt):
        # The observed action=send schema has no idempotency-key field: do not
        # pretend outbox_id/attempt were registered with the platform.
        return message_tool(action='send',target=destination,message=text)
    adapter=OwnerAlertAdapter(owner_destination,authorize_task,resolve_binding,invoke,
                              lambda raw:parse_message_result(raw,owner_destination))
    # Main's message-tool host must register 'async'. A known legacy synchronous
    # host may explicitly register 'sync'; no code executes during selection.
    adapter.requires_async=(message_mode=='async')
    return adapter
