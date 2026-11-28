"""Owner quota policy; no credentials, networking, or Gateway RPC.
Runtime is injected by an authorized native-tool custodian, never request JSON.
"""
import json
import math

POLICY_VERSION = 'owner-20261123-1629'
ROUTES = {
    'api': {'provider': 'openai-api', 'model': 'gpt-5.6-sol', 'billingRoute': 'api-key'},
    'subscription': {'provider': 'openai', 'model': 'gpt-6.1-sol', 'billingRoute': 'oauth-subscription'},
    'alternative': {'provider': 'qwen-token-plan', 'model': 'qwen3.8-flash', 'billingRoute': 'existing-authorized-plan'},
}
EXCEPTIONS = frozenset(('repair-installer', 'independent-reviewer'))
RECOVERABLE = frozenset(('COMPATIBILITY', 'EXECUTION_UNAVAILABLE', 'RATE_LIMIT'))

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def quota_value(snapshot, route, now, max_age):
    """Only applicable trusted windows, all required; conservative minimum.
    Source freshness allowance is supplied by the snapshot custodian, not data.
    API amount is remaining native units, NEVER subscription percentage.
    """
    s = snapshot.get(route, {}) if isinstance(snapshot,dict) else {}
    if not isinstance(s,dict):s={} 
    evidence = {k: s.get(k) for k in ('source', 'observedAt', 'state', 'windows',
        'remaining', 'unit', 'errorCategory', 'refreshing', 'routeId', 'authMode', 'accountScopeRef')}
    observed = s.get('observedAt')
    valid_time = (type(observed) in (int, float) and math.isfinite(observed)
                  and 0 <= now-observed <= max_age)
    identity = (s.get('routeId') == route and s.get('authMode') == ROUTES[route]['billingRoute']
                and bool(s.get('accountScopeRef')) and bool(s.get('source')))
    if not valid_time or not identity or s.get('state') != 'KNOWN' or s.get('errorCategory'):
        return None, evidence
    if route == 'api':
        v = s.get('remaining')
        return (v if type(v) in (int, float) and math.isfinite(v) and v >= 0
                and s.get('unit') else None), evidence
    windows = s.get('windows')
    if not isinstance(windows, list) or not windows:
        return None, evidence
    values = []
    for window in windows:
        if not isinstance(window,dict):return None,evidence
        v = window.get('remainingPercent'); reset = window.get('resetAt')
        if (type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100
                or type(reset) not in (int, float) or not math.isfinite(reset) or reset <= now):
            return None, evidence
        values.append(v)
    return min(values), evidence

def select(role, snapshot, now, allowed, max_age, excluded=()):
    """Pure decision. Caller supplies verified role/allow, not user task text."""
    reasons = []; evidence = {}
    order = (['alternative'] if role in EXCEPTIONS else
             ['api', 'subscription', 'alternative'] if role == 'main' else
             ['subscription', 'alternative'])
    for route in order:
        if route not in allowed:
            reasons.append(route+':NOT_AUTHORIZED'); continue
        if route in excluded:
            reasons.append(route+':RECOVERABLE_NO_EFFECT'); continue
        if route != 'alternative':
            value, source = quota_value(snapshot, route, now, max_age)
            evidence[route] = source
            if value is None:
                reasons.append(route+':UNKNOWN'); continue
            if route == 'api' and value == 0:
                reasons.append('api:ZERO'); continue
            if route == 'subscription' and (value <= 20 if role == 'main' else value < 5):
                reasons.append('subscription:THRESHOLD'); continue
        return dict(policyVersion=POLICY_VERSION, routeId=route, target=ROUTES[route],
                    reason=reasons+['PREFERRED_AVAILABLE' if route != 'alternative' else
                                    'ROLE_EXCEPTION' if role in EXCEPTIONS else 'AUTHORIZED_FALLBACK'],
                    quota=evidence)
    return dict(policyVersion=POLICY_VERSION, routeId=None, target=None,
                reason=reasons+['NO_AUTHORIZED_ROUTE'], quota=evidence)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS model_gateway_dispatch(
      tenant_id TEXT NOT NULL, request_id TEXT NOT NULL, decision_json TEXT,
      receipt_json TEXT, excluded_json TEXT NOT NULL DEFAULT '[]',
      PRIMARY KEY(tenant_id,request_id))''')


def mark_request(db, tenant, request):
    db.execute('INSERT INTO model_gateway_dispatch(tenant_id,request_id) VALUES (?,?)',
               (tenant, request))


def run_controlled(scheduler, row, now):
    """Called only AFTER existing scheduler authority/role/spec/module checks.
    A reserve/unknown or accepted receipt is query-only, including after crash.
    Native custodian owns Gateway authentication and atomic model/budget allow.
    """
    control = scheduler.control; db = scheduler.db
    identity = (row['tenant_id'], row['request_id'])
    runtime = getattr(control, 'gateway_runtime', None)
    if runtime is None:
        return {'request_id': row['request_id'], 'state': 'NOT_CONNECTED',
                'reason': 'GATEWAY_NATIVE_RUNTIME_NOT_INSTALLED'}
    record = db.execute('SELECT * FROM model_gateway_dispatch WHERE tenant_id=? AND request_id=?', identity).fetchone()
    context = {k: row[k] for k in ('tenant_id','task_id','attempt_id','request_id','role_id',
                                  'writer_principal','writer_fence','writer_epoch')}
    context['checkpoint'] = json.loads(row['checkpoint_json'])
    context['idempotencyKey'] = row['request_id']
    context['dispatchAttempt'] = row['attempts'] if row['state'] in ('RUNNING','UNKNOWN') else row['attempts']+1
    # query is required to be read-only and bound to original request, never execute.
    if row['state'] in ('RUNNING', 'UNKNOWN'):
        try:
            receipt = runtime.query(context)
        except Exception:
            return {'request_id': row['request_id'], 'state': 'UNKNOWN', 'reason': 'RECONCILE_REQUIRED'}
        return settle(scheduler, row, receipt, now, query=True)
    context['binding'] = {k: row[k] for k in ('provider_config_version','module_version',
        'skill_snapshot_sha256','work_spec_sha256','expected_input_tokens','max_output_tokens')}
    context['cancelRequested'] = bool(row['cancel_requested'])
    limits=db.execute('SELECT tenant_budget,task_budget,tpm_limit FROM model_runtime_limits WHERE tenant_id=? AND provider_id=?',
                      (row['tenant_id'],row['provider_id'])).fetchone()
    if limits is not None and (limits['tenant_budget'] is not None or limits['task_budget'] is not None):
        return {'request_id':row['request_id'],'state':'HOLD','reason':'UNKNOWN_COST_BUDGET_HOLD'}
    try:
        snapshot = runtime.snapshot(context)
    except Exception:
        snapshot = {}
    decision = select(row['role_id'], snapshot, now, runtime.allowed_routes(context),
                      runtime.max_snapshot_age, json.loads(record['excluded_json']))
    decision['source'] = {'provider': row['provider_id'], 'model': row['model_id']}
    with db:
        db.execute('UPDATE model_gateway_dispatch SET decision_json=? WHERE tenant_id=? AND request_id=?',
                   (canonical(decision),)+identity)
    if decision['routeId'] is None:
        return {'request_id': row['request_id'], 'state': 'HOLD', 'decision': decision}
    context['policyVersion'] = POLICY_VERSION
    context['decision'] = decision
    context['messages'] = json.loads(row['payload_json'])['messages']
    context['maxOutputTokens'] = row['max_output_tokens']
    # No Gateway/API credentials cross this interface. Admission must revalidate
    # native tool policy/model allow, writer binding, budget and package purpose.
    if runtime.admit(context) is not True:
        return {'request_id': row['request_id'], 'state': 'HOLD', 'reason': 'NATIVE_ADMISSION_DENIED'}
    db.execute('BEGIN IMMEDIATE')
    try:
        current=control.gateway.supervisor._task(row['task_id'])
        if (current['attempt_id']!=row['attempt_id'] or current['authority_state']!='VALID'
                or current['authority_valid_until'] is None or now>=current['authority_valid_until']
                or current['authority_caller_id']!=row['writer_principal']
                or current['fence']!=row['writer_fence'] or current['epoch']!=row['writer_epoch']):
            db.rollback();return {'state':'HOLD','reason':'STALE_WRITER_BEFORE_NATIVE_DISPATCH'}
        changed = db.execute("""UPDATE model_requests SET state='RUNNING',attempts=attempts+1,
          lease_owner=?,lease_until=?,last_heartbeat=?,updated_at=? WHERE tenant_id=? AND request_id=?
          AND state IN ('QUEUED','RETRY_WAIT') AND cancel_requested=0""",
          (scheduler.worker_id, now+row['timeout_seconds']+5, now, now)+identity).rowcount
        if changed != 1:
            db.rollback(); return {'state': 'LOST_RACE', 'request_id': row['request_id']}
        decision['source'] = {'provider': row['provider_id'], 'model': row['model_id']}
        db.execute('UPDATE model_gateway_dispatch SET decision_json=? WHERE tenant_id=? AND request_id=?',
                   (canonical(decision),)+identity)
        db.execute('''UPDATE model_requests SET checkpoint_json=? WHERE tenant_id=? AND request_id=?''',
                   (canonical(dict(context['checkpoint'], gateway={'state': 'CALL_RESERVED',
                     'requestId': row['request_id'], 'decision': decision})),)+identity)
        db.execute("UPDATE role_instances SET state='RUNNING',current_request_id=?,last_checkpoint_json=?,updated_at=? WHERE tenant_id=? AND instance_id=?",
                   (row['request_id'],canonical({'state':'CALL_RESERVED','decision':decision}),now,row['tenant_id'],row['instance_id']))
        control._audit(scheduler.worker_id, 'GATEWAY_CALL_RESERVED', row['request_id'], decision, now)
        db.commit()
    except Exception:
        db.rollback(); raise
    # Persist reservation BEFORE native tool dispatch. Timeout/transport/invalid
    # reply never means no effect. Restarts query this original request only.
    try:
        receipt = runtime.dispatch(context)
    except Exception:
        receipt = {'state': 'UNKNOWN', 'requestId': row['request_id']}
    active = dict(row); active['attempts'] += 1
    return settle(scheduler, active, receipt, now)


def settle(scheduler, row, receipt, now, query=False):
    db=scheduler.db; identity=(row['tenant_id'],row['request_id'])
    runtime=scheduler.control.gateway_runtime
    valid=(isinstance(receipt, dict) and receipt.get('requestId')==row['request_id']
           and receipt.get('state') in ('ACCEPTED','SUCCEEDED','FAILED','NO_EFFECT','UNKNOWN'))
    if not valid: receipt={'requestId':row['request_id'],'state':'UNKNOWN'}
    # Narrow receipt surface, not arbitrary provider logs or credentials.
    receipt={k:receipt[k] for k in ('requestId','state','runId','sessionKey','actualRoute',
             'errorCategory','checkpoint','result','usage') if k in receipt}
    if 'usage' in receipt:
        source=receipt['usage'] if isinstance(receipt['usage'],dict) else {}
        receipt['usage']={key:(source.get(key) if type(source.get(key)) is int
          and source[key]>=0 else None) for key in
          ('input_tokens','output_tokens','cached_tokens','reasoning_tokens')}
    state=receipt['state']; category=receipt.get('errorCategory')
    if state=='NO_EFFECT' and (receipt.get('runId') or receipt.get('sessionKey')):state='UNKNOWN'
    if state in ('ACCEPTED','SUCCEEDED') and not (receipt.get('runId') and receipt.get('sessionKey')):
        state='UNKNOWN'
    next_state={'ACCEPTED':'RUNNING','SUCCEEDED':'SUCCEEDED','FAILED':'FAILED',
                'UNKNOWN':'UNKNOWN','NO_EFFECT':'FAILED'}[state]
    db.execute('BEGIN IMMEDIATE')
    try:
        fresh=db.execute('SELECT * FROM model_requests WHERE tenant_id=? AND request_id=?',identity).fetchone()
        if (fresh is None or fresh['state'] not in ('RUNNING','UNKNOWN') or
            fresh['attempts']!=row['attempts']):
            db.rollback(); return {'request_id':row['request_id'],'state':'UNKNOWN','reason':'LATE_RESULT_REJECTED'}
        record=db.execute('SELECT * FROM model_gateway_dispatch WHERE tenant_id=? AND request_id=?',identity).fetchone()
        excluded=json.loads(record['excluded_json'])
        # NO_EFFECT is a trusted native receipt assertion, not inferred from HTTP.
        if (state=='NO_EFFECT' and category in RECOVERABLE and
                not receipt.get('runId') and not receipt.get('sessionKey') and
                row['attempts'] < runtime.max_attempts and not fresh['cancel_requested']):
            decision=json.loads(record['decision_json']); excluded.append(decision['routeId'])
            next_state='RETRY_WAIT'
        if fresh['cancel_requested'] and next_state in ('SUCCEEDED','FAILED','RETRY_WAIT'):
            next_state='CANCELLED'
        checkpoint=json.loads(fresh['checkpoint_json'])
        checkpoint['gatewayReceipt']=receipt
        changed=db.execute('''UPDATE model_requests SET state=?,error_kind=?,checkpoint_json=?,
            result_json=?,next_attempt_at=?,lease_owner=NULL,lease_until=NULL,updated_at=?
            WHERE tenant_id=? AND request_id=? AND attempts=? AND state IN ('RUNNING','UNKNOWN')''',
            (next_state,category,canonical(checkpoint),canonical(receipt.get('result')),
             now,now)+identity+(row['attempts'],)).rowcount
        if changed!=1: raise ValueError('GATEWAY_RECEIPT_CAS_FAILED')
        if next_state in ('SUCCEEDED','FAILED','CANCELLED','RETRY_WAIT','UNKNOWN'):
            # Trusted native receipt metadata only; absent usage is unknown.
            # Subscription/credits are not converted into cash or tokens.
            usage=receipt.get('usage') or {}
            route=receipt.get('actualRoute')
            route=route if isinstance(route,dict) else {}
            cached=usage.get('cached_tokens'); reasoning=usage.get('reasoning_tokens')
            if cached is not None and usage.get('input_tokens') is not None and cached>usage['input_tokens']:
                cached=None
            if reasoning is not None and usage.get('output_tokens') is not None and reasoning>usage['output_tokens']:
                reasoning=None
            db.execute('''INSERT INTO model_usage_attempts(
              tenant_id,request_id,attempt_number,provider_id,model_id,
              input_tokens,output_tokens,cost_state,cost_value,outcome,observed_at,
              task_id,attempt_id,cached_tokens,reasoning_tokens,billing_route)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(tenant_id,request_id,attempt_number) DO UPDATE SET
              input_tokens=COALESCE(excluded.input_tokens,model_usage_attempts.input_tokens),
              output_tokens=COALESCE(excluded.output_tokens,model_usage_attempts.output_tokens),
              cached_tokens=COALESCE(excluded.cached_tokens,model_usage_attempts.cached_tokens),
              reasoning_tokens=COALESCE(excluded.reasoning_tokens,model_usage_attempts.reasoning_tokens),
              provider_id=CASE WHEN excluded.provider_id='UNKNOWN' THEN model_usage_attempts.provider_id ELSE excluded.provider_id END,
              model_id=CASE WHEN excluded.model_id='UNKNOWN' THEN model_usage_attempts.model_id ELSE excluded.model_id END,
              billing_route=COALESCE(excluded.billing_route,model_usage_attempts.billing_route),
              outcome=excluded.outcome,observed_at=excluded.observed_at''',(
              row['tenant_id'],row['request_id'],fresh['attempts'],
              route.get('provider') if isinstance(route.get('provider'),str) else 'UNKNOWN',
              route.get('model') if isinstance(route.get('model'),str) else 'UNKNOWN',
              usage.get('input_tokens'),usage.get('output_tokens'),'UNKNOWN',None,
              next_state,now,fresh['task_id'],fresh['attempt_id'],cached,reasoning,
              route.get('billingRoute') if isinstance(route.get('billingRoute'),str) else None))
        db.execute('UPDATE model_gateway_dispatch SET receipt_json=?,excluded_json=? WHERE tenant_id=? AND request_id=?',
                   (canonical(receipt),canonical(excluded))+identity)
        db.execute("UPDATE role_instances SET state=?,current_request_id=?,last_checkpoint_json=?,updated_at=? WHERE tenant_id=? AND current_request_id=?",
                   ('RUNNING' if next_state=='RUNNING' else 'IDLE',row['request_id'] if next_state=='RUNNING' else None,canonical(checkpoint),now,row['tenant_id'],row['request_id']))
        scheduler.control._audit(scheduler.worker_id,'GATEWAY_RECEIPT',row['request_id'],
                                 {'state':next_state,'receipt':receipt},now)
        db.commit()
    except Exception:
        db.rollback(); raise
    return {'request_id':row['request_id'],'state':next_state,'receipt':receipt}


def main():
    import argparse
    import sys
    p=argparse.ArgumentParser(description='Consume trusted sanitized quota JSON; no live provider access')
    p.add_argument('--role',required=True);p.add_argument('--now',required=True,type=float)
    p.add_argument('--max-age',required=True,type=float)
    p.add_argument('--allowed',nargs='+',required=True,choices=sorted(ROUTES))
    a=p.parse_args()
    print(canonical(select(a.role,json.load(sys.stdin),a.now,a.allowed,a.max_age)))

if __name__=='__main__': main()
