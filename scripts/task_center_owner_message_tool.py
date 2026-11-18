"""Bind the original owner-alert host seam to an injected message tool.

Only the hosting runtime can supply the real messaging callable and trusted
scope/binding resolvers. This module neither accesses OpenClaw RPC nor grants
permissions, and does not install itself in a server or job.
"""
from task_center_owner_alert_adapter import OwnerAlertAdapter


def parse_message_result(raw):
    """Map observed Feishu send results conservatively; SENT never means ACK.

    A successful call, sentAt or a source-reply flag alone does not prove the
    target platform send has settled. Ambiguity, including inconsistent IDs,
    is UNKNOWN. No exact-attempt no-effect query is implied by this parser.
    """
    if not isinstance(raw,dict) or raw.get('ok') is not True or raw.get('channel')!='feishu' or raw.get('action')!='send':return None
    delivery=raw.get('messageDelivery')
    if not isinstance(delivery,dict) or delivery.get('status')!='settled':return None
    receipt=raw.get('receipt')
    receipt_id=receipt.get('primaryPlatformMessageId') if isinstance(receipt,dict) else None
    message_id=raw.get('messageId')
    if message_id is not None and receipt_id is not None and message_id!=receipt_id:return None
    identifier=message_id if message_id is not None else receipt_id
    if not isinstance(identifier,str) or not identifier or identifier!=identifier.strip() or len(identifier)>256:return None
    return {'state':'SENT','settled':True,'message_id':identifier}


def make_owner_message_adapter(owner_destination, authorize_task, resolve_binding, message_tool):
    """The host injects the existing functions.message capability, not an RPC.

    ``message_tool`` must be a host callable for the actual main tool. The
    current platform interface does not provide an idempotency key or exact
    attempt lookup; local original outbox intent still prevents blind retries.
    """
    if not isinstance(owner_destination,str) or not owner_destination.startswith('user:') or len(owner_destination)<=5:
        raise ValueError('OWNER_DIRECT_DESTINATION_REQUIRED')
    if not callable(message_tool):raise ValueError('HOST_MESSAGE_TOOL_REQUIRED')
    def invoke(destination,text,outbox_id,delivery_attempt):
        # The observed action=send schema has no idempotency-key field: do not
        # pretend outbox_id/attempt were registered with the platform.
        return message_tool(action='send',target=destination,message=text)
    return OwnerAlertAdapter(owner_destination,authorize_task,resolve_binding,invoke,parse_message_result)
