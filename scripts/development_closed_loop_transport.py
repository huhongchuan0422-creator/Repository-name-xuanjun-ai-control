"""Fixed PR17 mechanical delivery for the existing Supervisor outbox.

No model calls, no task authority, no new queue. Unknown external write effects
are reconciled by marker before any subsequent POST.
"""
from __future__ import print_function

import json
import re
import subprocess

REPOSITORY='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
PR_NUMBER=17
OWNER='huhongchuan0422-creator'
MARKER_PREFIX='<!-- XJ_TASK45_OUTBOX '


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _marker(outbox_id):
    if not isinstance(outbox_id,str) or re.fullmatch(r'[0-9a-f]{64}',outbox_id) is None:
        raise ValueError('EXACT_OUTBOX_ID_REQUIRED')
    return MARKER_PREFIX+outbox_id+' -->'


class FixedPr17Transport(object):
    def __init__(self, gh_bin='/usr/bin/gh', home='/tmp', path='/usr/bin:/bin',
                 runner=None):
        self.gh_bin=gh_bin;self.home=home;self.path=path
        self.runner=runner or subprocess.run

    def _run(self, argv, input_bytes=None):
        result=self.runner(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           input=input_bytes,timeout=30,check=False,
                           env={'HOME':self.home,'PATH':self.path,'LANG':'C.UTF-8'})
        if result.returncode:
            raise RuntimeError('GITHUB_TRANSPORT_FAILED')
        return json.loads(result.stdout.decode('utf-8'))

    def _assert_owner(self):
        value=self._run([self.gh_bin,'api','user'])
        if value.get('login')!=OWNER:
            raise ValueError('GITHUB_ACCOUNT_IDENTITY_MISMATCH')

    def reconcile(self,row):
        if not isinstance(row,dict) or not {'outbox_id','payload_json'} <= set(row):
            raise ValueError('EXACT_OUTBOX_ROW_REQUIRED')
        outbox_id=row['outbox_id']
        marker=_marker(outbox_id)
        expected_payload=json.loads(row['payload_json'])
        rows=self._run([self.gh_bin,'api',
            'repos/'+REPOSITORY+'/issues/'+str(PR_NUMBER)+'/comments',
            '--paginate','--slurp'])
        matches=[]
        def walk(value):
            if isinstance(value,list):
                for item in value:walk(item)
            elif isinstance(value,dict):
                body=value.get('body')
                login=(value.get('user') or {}).get('login')
                if (isinstance(body,str) and body.startswith(marker+'\n')
                        and login==OWNER and isinstance(value.get('id'),int)):
                    try:
                        envelope=json.loads(body[len(marker)+1:])
                    except (ValueError,TypeError):
                        raise ValueError('MALFORMED_EXTERNAL_RECEIPT')
                    if (isinstance(envelope,dict)
                            and envelope.get('schema')==1
                            and envelope.get('kind')=='TASK45_OUTBOX_DELIVERY'
                            and envelope.get('outbox_id')==outbox_id
                            and 'payload' in envelope):
                        if envelope['payload']!=expected_payload:
                            raise ValueError('CONFLICTING_EXTERNAL_RECEIPT')
                        matches.append(value)
                    else:
                        raise ValueError('MALFORMED_EXTERNAL_RECEIPT')
        walk(rows)
        if len(matches)>1:
            raise ValueError('DUPLICATE_EXTERNAL_RECEIPT')
        if not matches:return None
        return {'message_id':str(matches[0].get('id')),
                'outbox_id':outbox_id,'repository':REPOSITORY,
                'pr_number':PR_NUMBER}

    def send(self,row):
        if not isinstance(row,dict) or not {'outbox_id','payload_json'} <= set(row):
            raise ValueError('EXACT_OUTBOX_ROW_REQUIRED')
        outbox_id=row['outbox_id'];marker=_marker(outbox_id)
        existing=self.reconcile(row)
        if existing is not None:return existing
        self._assert_owner()
        payload=json.loads(row['payload_json'])
        body=marker+'\n'+_canonical({
            'schema':1,'kind':'TASK45_OUTBOX_DELIVERY',
            'outbox_id':outbox_id,'payload':payload})
        request=json.dumps({'body':body},sort_keys=True,separators=(',',':')).encode('utf-8')
        try:
            value=self._run([self.gh_bin,'api',
                'repos/'+REPOSITORY+'/issues/'+str(PR_NUMBER)+'/comments',
                '--method','POST','--input','-'],input_bytes=request)
        except Exception:
            # External write may have succeeded. Caller must reconcile later.
            raise
        if ((value.get('user') or {}).get('login')!=OWNER
                or value.get('body')!=body
                or not isinstance(value.get('id'),int)):
            raise ValueError('UNTRUSTED_EXTERNAL_RECEIPT')
        return {'message_id':str(value['id']),'outbox_id':outbox_id,
                'repository':REPOSITORY,'pr_number':PR_NUMBER}


def deliver_one(supervisor,transport,now):
    rows=supervisor.due_outbox(now=now,limit=1)
    if not rows:return {'state':'NO_DUE_OUTBOX','authority_effect':'NONE'}
    row=rows[0]
    try:
        receipt=transport.reconcile(row)
        if receipt is None:
            receipt=transport.send(row)
    except Exception as error:
        result=supervisor.outbox_result(row['outbox_id'],False,now=now,
                                        error=type(error).__name__)
        return dict(result,state='DELIVERY_RECONCILE_REQUIRED',
                    authority_effect='NONE')
    result=supervisor.outbox_result(row['outbox_id'],True,now=now)
    return dict(result,state='DELIVERED_ACKNOWLEDGED',receipt=receipt,
                authority_effect='NONE')
