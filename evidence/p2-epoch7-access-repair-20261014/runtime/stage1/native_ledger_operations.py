"""Typed native operations over the existing ledger, without dispatch authority."""
def execute(ledger, value):
    if (isinstance(value,dict) and value.get('operation')=='owner_delivery' and
            set(value)=={'operation','request'}):
        return ledger.owner_feishu_endpoint.execute(value['request'])
    if not isinstance(value, dict) or value.get('operation') not in ('preflight', 'read', 'cas', 'guard', 'receipt', 'tool_guard'):
        raise ValueError('native bridge operation rejected')
    if value['operation'] == 'preflight':
        with ledger._transaction() as conn:
            ledger._validate_schema(conn)
            ledger._validate_side_schema(conn)
        return {'canonical_existing': True, 'outbox_existing': True}
    if value['operation'] == 'tool_guard':
        return ledger.native_tool_observation(value['request']['session_key'])
    request = value['request']
    if value['operation'] == 'receipt':
        return ledger.native_receipt_observation(request)
    if value['operation'] == 'cas':
        return ledger.native_compare_set(request, value['expected'], value['execution'])
    observed = ledger.native_observation(request)
    return True if value['operation'] == 'guard' else observed

