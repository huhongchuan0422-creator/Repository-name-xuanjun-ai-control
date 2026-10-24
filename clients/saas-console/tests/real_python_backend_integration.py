#!/usr/bin/env python3
"""SaaS isolated integration against the exact e7 PR122 review-only artifact.
Synthetic identities only. NOT Hosted/production/customer/payment/deployment evidence.
"""
import base64, hashlib, http.client, json, os, subprocess, sys, time
from http.cookies import SimpleCookie
from pathlib import Path

EXPECTED_COMMIT='e7f75975c4ab4eedba68306212a2bac6c067a1c3'
EXPECTED_TREE='d001cfd9855ed3a7758f6286db5cae7d45cce403'
HOST='wenwenwenyiyiyi.work'; ORIGIN='https://wenwenwenyiyiyi.work'; COOKIE='__Host-xj_customer'
root=Path(os.environ.get('XJ_PR122_E7_ROOT','')).resolve()
if not str(root) or not (root/'CUSTOMER_MANIFEST.json').is_file(): raise SystemExit('HOLD_MISSING_E7_ARTIFACT_ROOT')
manifest=json.loads((root/'CUSTOMER_MANIFEST.json').read_text())
if manifest.get('source_commit')!=EXPECTED_COMMIT: raise SystemExit('HOLD_E7_COMMIT_MISMATCH:'+str(manifest.get('source_commit')))
if manifest.get('source_tree')!=EXPECTED_TREE: raise SystemExit('HOLD_E7_TREE_MISMATCH:'+str(manifest.get('source_tree')))
files=manifest.get('files') or []
if len(files)!=102: raise SystemExit('HOLD_E7_MANIFEST_COUNT:'+str(len(files)))
for rec in files:
    p=root/rec['path']
    if not p.is_file(): raise SystemExit('HOLD_E7_FILE_MISSING:'+rec['path'])
    if hashlib.sha256(p.read_bytes()).hexdigest()!=rec['sha256']: raise SystemExit('HOLD_E7_FILE_HASH:'+rec['path'])

proc=subprocess.Popen([sys.executable,'-B','-m','tests.pr122_customer_browser_server'],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
try:
    line=proc.stdout.readline().strip()
    if not line: raise SystemExit('HOLD_E7_FIXTURE_START:'+proc.stderr.read())
    info=json.loads(line); port=info['port']; control=info['control_port']
    if info.get('scope')!='ISOLATED_FIXTURE_NOT_PRODUCTION' or info.get('fixture_signer')!='TEST_ONLY': raise SystemExit('HOLD_E7_FIXTURE_SCOPE')
    def raw(path,body=None,headers=None,method=None,port_override=None):
        c=http.client.HTTPConnection('127.0.0.1',port_override or port,timeout=10)
        h={'Host':HOST,**(headers or {})}; data=None
        if body is not None:
            data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
            h={'Origin':ORIGIN,'Content-Type':'application/json','Content-Length':str(len(data)),**h}
        c.request(method or ('POST' if body is not None else 'GET'),path,data,h); r=c.getresponse(); b=r.read(); out=(r.status,dict(r.getheaders()),b); c.close(); return out
    def req(path,body=None,headers=None,method=None):
        s,h,b=raw('/customer/center/'+path,body,headers,method)
        try:d=json.loads(b) if b else {}
        except Exception:d={'_raw':b.decode(errors='replace')}
        return s,h,d
    def login(who):
        s,h,d=req('api/login',{'email':who+'@example.com','password':'correct-password-123'}); assert s==200,(s,d)
        assert 'csrf' in d and 'token' not in d
        ck=SimpleCookie();ck.load(h['Set-Cookie']);return {'Cookie':COOKIE+'='+ck[COOKIE].value,'X-CSRF-Token':d['csrf']}

    owner=login('owner'); reviewer=login('reviewer'); other=login('other')
    s,_,me=req('api/me',headers=owner); assert s==200 and [p['id'] for p in me['projects']]==['project-a']
    s,_,check=req('api/checklist/project-a',headers=owner); assert s==200
    item=next(x for x in check['items'] if x['submission_type']=='PRIVATE_DOCUMENT')
    pdf=b'%PDF-1.7\nsynthetic SaaS material\n%%EOF'
    s,_,saved=req('api/save',{'project':'project-a','item':item['id'],'revision':item['revision'],'kind':'DOCUMENT','content':base64.b64encode(pdf).decode(),'expires':item.get('valid_until')},owner)
    assert s==200 and saved['revision']==item['revision']+1,(s,saved)
    s,_,check2=req('api/checklist/project-a',headers=owner); item2=next(x for x in check2['items'] if x['id']==item['id']); assert item2['revision']==saved['revision']
    s,_,denied=req('api/checklist/project-a',headers=other); assert s==403 and denied['error']=='权限不足、凭据失效或请求不符合要求',(s,denied)

    s,_,pre=req('api/previews/project-a',headers=owner); assert s==200 and pre['pages']; page=next((x for x in pre['pages'] if x['path']=='/project/consumer/'),pre['pages'][0]); v1=page['sha256']
    s,_,_=req('api/change_context',{'project':'project-a','page':page['path'],'version':v1},owner); assert s==200
    s,_,created=req('api/change_submit',{'project':'project-a','page':page['path'],'version':v1,'text':'将「Welcome」改为「Welcomes」','intent':'RECTIFICATION'},owner); assert s==200; case=created['id']
    s,_,cases=req('api/changes/project-a',headers=owner); assert s==200 and any(x['id']==case for x in cases['cases'])

    s,_,rcases=req('api/changes/project-a',headers=reviewer); ce=next(x for x in rcases['cases'] if x['id']==case); rev=ce['events'][-1]['seq']
    s,_,assessed=req('api/change_assess',{'project':'project-a','case':case,'revision':rev,'category':'IN_SCOPE_SMALL','minutes':1,'lines':[],'evidence':[],'explanation':'单处已授权展示文案小改'},reviewer); assert s==200 and assessed['state']=='FREE_APPROVED'
    s,_,queued=req('api/change_small_edit',{'project':'project-a','case':case},reviewer); assert s==200; job=queued['id']
    state=None
    for _ in range(80):
        s,_,state=req('api/edit_candidate/project-a/'+job,headers=reviewer); assert s==200
        if state['state'] in ('CANDIDATE_READY','HOLD_UNKNOWN'): break
        time.sleep(.05)
    assert state['state']=='CANDIDATE_READY',state
    s,_,_=raw('/publish-ready',body={},method='POST',port_override=control); assert s==204

    s,_,pre2=req('api/previews/project-a',headers=owner); page2=next(x for x in pre2['pages'] if x['path']==page['path']); v2=page2['sha256']; assert v2!=v1
    s,_,updates=req('api/change_updates',{'project':'project-a','page':page['path'],'version':v2},owner); u=next(x for x in updates['updates'] if x['case']==case); assert u['before_sha256']==v1 and u['after_sha256']==v2 and u['state']=='AWAIT_RETEST'
    s,_,rr=req('api/change_retest',{'project':'project-a','case':case,'revision':u['revision'],'page':page['path'],'version':v2,'delivery_sha256':u['delivery_sha256'],'action':'ACCEPT','reason':'同版隔离复验通过'},owner); assert s==200 and rr['state']=='RETEST_ACCEPTED' and rr['automatic_charge'] is False
    s,_,final=req('api/changes/project-a',headers=owner); assert next(x for x in final['cases'] if x['id']==case)['events'][-1]['kind']=='RETEST'

    s,_,lo=req('api/logout',{},owner); assert s==200 and lo['logged_out'] is True
    s,_,lost=req('api/me',headers={'Cookie':owner['Cookie']}); assert s==403 and lost['error']=='权限不足、凭据失效或请求不符合要求'
    print(json.dumps({'status':'PASS','scope':info['scope'],'source_commit':EXPECTED_COMMIT,'source_tree':EXPECTED_TREE,'manifest_files':102,'save_revision':saved['revision'],'v1':v1,'v2':v2,'retest':rr['state'],'cross_project_403':True,'post_logout_403':True,'browser':'NOT_VERIFIED'},ensure_ascii=False))
finally:
    proc.terminate()
    try:proc.wait(timeout=3)
    except subprocess.TimeoutExpired:proc.kill()
