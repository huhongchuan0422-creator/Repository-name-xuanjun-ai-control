"""Safe carrier archive scanner. Does not install or execute archives."""
import hashlib, io, json, tarfile

def scan(data, expected):
    seen=set(); total=0;scope=None
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:*') as t:
        for m in t:
            p=m.name
            if not p or p.startswith('/') or any(v in ('','.','..') for v in p.split('/')): raise ValueError('UNSAFE_PATH')
            if p in seen or not (m.isfile() or m.isdir()): raise ValueError('UNSAFE_MEMBER')
            seen.add(p)
            if m.isdir():
                if expected.get(p)!={'type':'directory'}:raise ValueError('DIRECTORY_MISMATCH')
            else:
                total+=m.size
                if m.size>67108864 or total>268435456:raise ValueError('SIZE_LIMIT')
                content=t.extractfile(m).read(m.size+1)
                if p=='TOOL_SCOPE.json':scope=json.loads(content.decode('utf-8'))
                if expected.get(p)!={'type':'file','size':len(content),'sha256':hashlib.sha256(content).hexdigest()} or len(content)!=m.size:raise ValueError('FILE_MISMATCH')
    if 'TOOL_SCOPE.json' not in seen or scope is None:raise ValueError('CARRIER_TOOL_SCOPE_REQUIRED')
    read={'task_candidate_status','task_capabilities','task_development_gateway_readback','task_development_status','task_dispatch_contract','task_dispatch_status','task_get','task_list','task_query_result','task_read_context','task_result_recovery_status'}
    write={'task_accept_candidate','task_accept_result_recovery','task_assign_role','task_cancel_dispatch','task_claim','task_development_apply','task_development_continue_review','task_development_finalize','task_development_gateway','task_development_gateway_candidate','task_development_gateway_test_event','task_development_review','task_development_verify_tests','task_dispatch','task_prepare_result_recovery','task_report_progress','task_request_review','task_review_candidate','task_review_result_recovery','task_save_checkpoint','task_submit','task_submit_artifact','task_submit_candidate'}
    if set(scope.get('read_only_tools',[]))!=read or set(scope.get('write_tools',[]))!=write:raise ValueError('CARRIER_TOOL_SCOPE_INVALID')
    if (scope.get('schema')!=1 or scope.get('default_off') is not True or scope.get('default_mode')!='READ_ONLY' or scope.get('allowed_write_tools')!=[] or scope.get('unknown_dynamic_tools')!='DENY' or len(set(scope.get('read_only_tools',[])))!=11 or len(set(scope.get('write_tools',[])))!=23 or set(scope.get('read_only_tools',[]))&set(scope.get('write_tools',[]))):raise ValueError('CARRIER_TOOL_SCOPE_INVALID')
    if seen!=set(expected):raise ValueError('MEMBER_SET_MISMATCH')
    return seen
