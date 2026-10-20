"""Batch continuation over PR99's existing controller; no host actions bundled.

Call only from the existing admitted controller process with its original held
descriptors, journal, plan and authenticated execute/query adapters. This module
does not create a writer, fence, sudo rule, journal or production receipt.
"""


class BatchHold(RuntimeError):
    pass


def run_batch(controller, plan, dispatchers, queries, progress):
    """Run the exact remaining original stages, halting on any uncertainty.

    Preflight checks every required adapter before the first side effect. An
    existing intent is passed to ExistingFdController.perform(), whose query-only
    recovery semantics remain authoritative. A recovered unrecorded result ends
    this invocation; it never automatically advances to the next stage.
    """
    contract = controller.m
    stages = tuple(contract.STEPS)
    if (type(plan) is not dict or plan.get('steps') != list(stages)
            or type(dispatchers) is not dict or type(queries) is not dict
            or not callable(progress)):
        raise BatchHold('BATCH_INPUT_INVALID')
    missing = [stage for stage in stages
               if not callable(dispatchers.get(stage))
               or not callable(queries.get(stage))]
    if missing:
        raise BatchHold('MISSING_REAL_ADAPTERS:' + ','.join(missing))
    claim, events, _ = controller.load()
    if claim.get('plan') != plan or claim.get('plan_digest') != contract.digest(plan):
        raise BatchHold('ORIGINAL_PLAN_MISMATCH')
    if any(event.get('type') in ('UNKNOWN', 'TERMINAL') for event in events):
        raise BatchHold('EXISTING_UNKNOWN_OR_TERMINAL')
    previous = claim['plan_digest']
    completed = []
    for stage in stages:
        req = contract.request(plan, stage, previous)
        intents = [event for event in events
                   if event.get('type') == 'INTENT'
                   and event.get('request', {}).get('operation_id') == req['operation_id']]
        results = [event['receipt'] for event in events
                   if event.get('type') == 'RESULT'
                   and event.get('receipt', {}).get('operation_id') == req['operation_id']]
        if len(intents) > 1 or len(results) > 1 or (results and not intents):
            raise BatchHold('ORIGINAL_HISTORY_CONFLICT')
        recovering = bool(intents and not results)
        if intents and intents[0]['request'] != req:
            raise BatchHold('ORIGINAL_INTENT_MISMATCH')
        progress({'stage': stage, 'state': 'REUSED' if results else
                  'QUERY_ONLY' if recovering else 'STARTING'})
        receipt = controller.perform(req, dispatchers[stage], queries[stage])
        contract.validate_receipt(receipt, req)
        if receipt['status'] != 'SUCCEEDED':
            progress({'stage': stage, 'state': 'FAILED_PRESERVED'})
            raise BatchHold('STAGE_FAILED:' + stage)
        if recovering:
            progress({'stage': stage, 'state': 'RESOLVED_REQUIRES_RECONCILIATION'})
            raise BatchHold('RECOVERED_RESULT_NO_AUTOMATIC_CONTINUATION')
        completed.append(stage)
        previous = contract.digest(receipt)
        progress({'stage': stage, 'state': 'SUCCEEDED'})
        # Reload the original history after each stage; never retain a fabricated
        # local journal or infer success from process exit or a printed marker.
        current, events, _ = controller.load()
        if current != claim:
            raise BatchHold('ORIGINAL_PLAN_CHANGED')
    return {'status': 'ORIGINAL_STAGES_COMPLETED', 'stages': completed,
            'last_receipt_digest': previous}
