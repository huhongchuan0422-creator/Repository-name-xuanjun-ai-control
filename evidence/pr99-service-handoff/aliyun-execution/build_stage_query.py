"""Query only the consumed Owner code-stage invocation, never RunCommand."""
from pathlib import Path

base=Path(__file__).parent
old=(base/'source_result_diagnostic.py').read_text()
program=old.replace("('tokyo', CN, 'ap-northeast-1', '68985c531add4e90a131aef703a389e6', 'iZ6wee8q9z4t03hvqumwfhZ')", "('domestic', CN, 'cn-shanghai', '3a22c458934142eea89ec6e3bf481a57', 'iZvt5t8tlrm8oiZ')")
program=program.replace('t-jpn70exx16tf280','t-sh070fl01lqes5c').replace('68985c531add4e90a131aef703a389e6','3a22c458934142eea89ec6e3bf481a57').replace('swas.ap-northeast-1.aliyuncs.com','swas.cn-shanghai.aliyuncs.com').replace("RegionId='ap-northeast-1'","RegionId='cn-shanghai'")
program=program.replace('pr99-source-result-','pr99-owner-stage-query-').replace('PR99_SOURCE_RESULT_DIAGNOSTIC_RECEIPT','PR99_OWNER_STAGE_QUERY_RECEIPT').replace('ORIGINAL_SOURCE_RESULT_DIAGNOSTIC_ONLY','ORIGINAL_OWNER_STAGE_RESULT_QUERY_ONLY')
needle="    for line in raw.splitlines()[-40:]:"
replacement=needle+'''
        try:
            value=json.loads(line)
            if type(value)is dict and set(value)=={'status','error_type','code','retry_allowed'}:
                row={'status':safe(value['status']),'exception':safe(value['error_type'])}
                if type(value['code'])is str and re.fullmatch('[A-Z0-9_]{1,160}',value['code']):row['code']=value['code']
                rows.append(row)
        except ValueError:pass
'''
assert program.count(needle)==1
program=program.replace(needle,replacement)
program=program.replace("    print('PR99_FAILURE_QUERY_REDACTION_PASS_SIX_CASES_NO_CLOUD',flush=True)","    assert failure_projection(json.dumps({'status':'OWNER_START_STAGE_HOLD','error_type':'HTTPError','code':'PRIVATE_DETAIL_WITHHELD','retry_allowed':False}))[0]['exception']=='HTTPError'\n    print('PR99_OWNER_STAGE_QUERY_REDACTION_PASS_NO_HOST_COMMAND',flush=True)")
assert 'RunCommand' not in program
(base/'owner_stage_result_query.py').write_text(program)
workflow=(base/'pr99-source-result-diagnostic.yml').read_text()
embedded='\n'.join('          '+line for line in old.rstrip('\n').split('\n'))
replacement='\n'.join('          '+line for line in program.rstrip('\n').split('\n'))
assert workflow.count(embedded)==2
workflow=workflow.replace(embedded,replacement).replace('pr99-source-result-','pr99-owner-stage-query-')
workflow=workflow.replace('PR99 source result metadata query only','PR99 Owner helper failed result query only')
(base/'pr99-owner-stage-query.yml').write_text(workflow)
print('OWNER_STAGE_QUERY_ONLY_BUILD_COMPLETE')
