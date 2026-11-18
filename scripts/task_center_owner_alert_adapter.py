"""Host-injected owner alert adapter; no channel credentials or tool RPC.

The host must supply already-authorized task scope and task-to-owner bindings,
its real existing messaging tool invocation, and a parser for that tool's
actual platform result. This module never discovers, grants or sends by itself.
"""

class OwnerAlertAdapter:
    def __init__(self, owner_destination, authorize_task, resolve_binding,
                 invoke_message, parse_platform_result):
        if (not isinstance(owner_destination,str) or not owner_destination
            or any(not callable(x) for x in (authorize_task,resolve_binding,invoke_message,parse_platform_result))):
            raise ValueError('TRUSTED_OWNER_HOST_BINDING_REQUIRED')
        self._owner=owner_destination
        self._authorize=authorize_task
        self._binding=resolve_binding
        self._invoke=invoke_message
        self._parse=parse_platform_result

    def resolve_destination(self, packet):
        """Destination confirmation is not task read or send authorization."""
        try:
            if (not isinstance(packet,dict) or not isinstance(packet.get('alert'),dict)
                or packet['alert'].get('action')!='HANDOFF_CONTEXT_INCOMPLETE'
                or any(not isinstance(packet.get(k),str) or not packet[k] for k in ('tenant_id','task_id','attempt_id','outbox_id'))):return None
            # Both calls are host-controlled, local, independent of request body.
            if self._authorize(packet['tenant_id'],packet['task_id'],packet['attempt_id']) is not True:return None
            destination=self._binding(packet['tenant_id'],packet['task_id'],packet['attempt_id'])
            return self._owner if destination==self._owner else None
        except Exception:return None

    def send(self, destination, packet):
        # Recheck task scope and the owner-only destination immediately before
        # invoking the injected existing tool; do not serialize credentials.
        if destination!=self._owner or self.resolve_destination(packet)!=destination:
            raise ValueError('OWNER_ALERT_BINDING_UNAVAILABLE')
        text='任务中心交接存在缺项或停工，请查看受保护任务记录。任务：%s；尝试：%s。' % (packet['task_id'],packet['attempt_id'])
        return self._invoke(destination,text,packet['outbox_id'],packet['delivery_attempt'])

    def interpret_result(self, destination, packet, raw):
        if destination!=self._owner:return None
        try: result=self._parse(raw)
        except Exception:return None
        if not isinstance(result,dict) or result.get('settled') is not True:return None
        if result.get('state')=='SENT':ref=result.get('message_id')
        elif result.get('state')=='FAILED':ref=result.get('receipt_ref')
        else:return None
        if not isinstance(ref,str) or not ref or ref!=ref.strip() or len(ref)>256:return None
        return {'state':result['state'],'receipt_ref':ref}

    def reconcile(self, packet):
        # No actual exact-attempt settled/no-effect query capability supplied.
        # Do not infer NOT_SENT from absence, timeout, or a successful send API.
        return None
