"""Concrete fixed PR17 transport. Persistence stays in the existing pipeline.

No shell, paid API, extra ledger or automatic retry of uncertain writes.
"""
import hashlib
import json
import os
import re
import stat
import subprocess

from native_child_adapter import NativeContractError


class FixedPr17GithubNotifier(object):
    REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
    OWNER = 'huhongchuan0422-creator'
    PR = 17
    REPORT_KEYS = frozenset(['task_id','spec_hash','fence','epoch','commit','pr',
                             'qa_commit','state','production_pass'])

    def __init__(self, executable, home, path, runner=None):
        for value in (executable,home):
            if not isinstance(value,str) or not os.path.isabs(value) or os.path.realpath(value)!=value:
                raise NativeContractError('canonical GitHub transport paths required')
        self.executable,self.home,self.path=executable,home,path
        self.runner=runner or subprocess.run

    def _call(self, args, payload=None):
        info=os.lstat(self.executable)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0
                or info.st_mode & 0o022 or not info.st_mode & 0o111):
            raise NativeContractError('GitHub binary is not trusted')
        result=self.runner([self.executable,'api']+args,
            input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={'HOME':self.home,'PATH':self.path,'LANG':'C.UTF-8',
                 'GIT_TERMINAL_PROMPT':'0'},timeout=60,check=False)
        if result.returncode or len(result.stdout)>16*1024*1024:
            raise NativeContractError('GitHub effect/receipt unconfirmed; do not replay')
        return json.loads(result.stdout.decode('utf-8','strict'))

    @staticmethod
    def _key(key):
        if not isinstance(key,str) or not re.fullmatch(r'[0-9a-f]{64}',key):
            raise NativeContractError('exact event key required')
        return '<!-- XJ_P2_RESULT '+key+' -->'

    def reconcile(self, idempotency_key):
        marker=self._key(idempotency_key)
        pages=self._call(['repos/'+self.REPOSITORY+'/issues/17/comments?per_page=100',
                          '--paginate','--slurp'])
        if not isinstance(pages,list) or any(not isinstance(p,list) for p in pages):
            raise NativeContractError('GitHub comment inventory unconfirmed')
        matches=[]
        for page in pages:
            for row in page:
                if (isinstance(row,dict) and isinstance(row.get('body'),str)
                        and row['body'].split('\n',1)[0]==marker
                        and row.get('user',{}).get('login')==self.OWNER):
                    if type(row.get('id')) is not int or row['id']<1:
                        raise NativeContractError('GitHub result identity unconfirmed')
                    matches.append(row)
        if len(matches)>1:
            raise NativeContractError('duplicate external result requires reconciliation')
        if not matches:return None
        return {'idempotency_key':idempotency_key,'message_id':str(matches[0]['id'])}

    def send(self, report, idempotency_key):
        marker=self._key(idempotency_key)
        if (not isinstance(report,dict) or set(report)!=self.REPORT_KEYS
                or report['production_pass'] is not False):
            raise NativeContractError('bounded code-only report required')
        raw=json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False)
        if len(raw.encode('utf-8'))>8192:
            raise NativeContractError('bounded report required')
        if hashlib.sha256(raw.encode('utf-8')).hexdigest()!=idempotency_key:
            raise NativeContractError('report event digest mismatch')
        identity=self._call(['user'])
        if not isinstance(identity,dict) or identity.get('login')!=self.OWNER:
            raise NativeContractError('fixed repository Owner GitHub identity required')
        existing=self.reconcile(idempotency_key)
        if existing is not None:return existing
        body=marker+'\nP2 code result; production acceptance is false.\n'+raw
        data=json.dumps({'body':body},ensure_ascii=False).encode('utf-8')
        result=self._call(['repos/'+self.REPOSITORY+'/issues/17/comments',
                           '--method','POST','--input','-'],data)
        if (not isinstance(result,dict) or type(result.get('id')) is not int
                or result['id']<1 or result.get('body')!=body
                or result.get('user',{}).get('login')!=self.OWNER):
            raise NativeContractError('GitHub send receipt unconfirmed; do not replay')
        return {'idempotency_key':idempotency_key,'message_id':str(result['id'])}
