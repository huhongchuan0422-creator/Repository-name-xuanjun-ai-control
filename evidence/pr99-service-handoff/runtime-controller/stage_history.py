"""New pure semantic validator for the published original PR99 event format.

Does not import or republish the restricted 40-file history implementation.
Admitting this validator still requires the original independent review channel.
Recovered UNKNOWN is settled for evidence only; automatic continuation is denied.
"""

def verify(contract, plan, events):
    pending = None
    previous = contract.digest(plan)
    completed = []
    attempted = []
    failed = False
    recovered_unknown = False
    terminal = False
    containment = []
    containment_failed = False
    for event in events:
        if type(event) is not dict or terminal:
            return False
        kind = event.get('type')
        if kind == 'INTENT':
            if set(event) != {'type','request'} or pending is not None or recovered_unknown:
                return False
            req = event['request']
            if type(req) is not dict:
                return False
            if failed:
                if not containment:
                    return False
                stage = containment.pop(0)
            else:
                if len(completed) >= len(contract.STEPS):
                    return False
                stage = contract.STEPS[len(completed)]
            if req != contract.request(plan,stage,previous):
                return False
            pending = req
            attempted.append(stage)
        elif kind == 'UNKNOWN':
            if (set(event) != {'type','operation_id'} or pending is None or recovered_unknown
                    or event['operation_id'] != pending['operation_id']):
                return False
            recovered_unknown = True
        elif kind == 'RESULT':
            if set(event) != {'type','receipt'} or pending is None:
                return False
            try:
                result = contract.validate_receipt(event['receipt'],pending)
            except (ValueError,TypeError,KeyError,contract.Hold):
                return False
            previous = contract.digest(result)
            completed.append(pending['stage'])
            if result['status'] == 'FAILED':
                if failed:
                    containment_failed = True
                    containment = []
                else:
                    failed = True
                    containment = (['restore_route'] if 'cutover_route' in attempted else [])
                    if 'install_stopped' in attempted:
                        containment.append('stop_owned')
            pending = None
        elif kind == 'TERMINAL':
            if set(event) != {'type','status'} or pending is not None or recovered_unknown:
                return False
            if containment_failed:
                expected = 'CONTAINMENT_FAILED_HOLD'
            elif failed and not containment:
                expected = 'FAILED_PRESERVED_NO_SOURCE_RESUME'
            elif completed == list(contract.STEPS):
                expected = 'FIXTURE_TRANSACTION_SUCCEEDED'
            else:
                return False
            if event['status'] != expected:
                return False
            terminal = True
        else:
            return False
    return True
