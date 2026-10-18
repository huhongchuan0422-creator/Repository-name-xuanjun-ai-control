"""Service glue for the existing authenticated channel; never a public endpoint.

The channel must authenticate principal, and the protected host adapter must
return real independent transaction/backup/readback facts. No defaults, mock
provider, key generation, cloud dispatch or installer launcher ships here.
"""
import base64
import json
import re
from receipt_provider import canonical, digest, need
from authority_store import AuthorityStore

HOST_OPERATIONS=frozenset(('authorize_first_admission','authenticate_native_recovery',
    'verify_completed_phase','verify_phase_commit','reconcile_native_intent',
    'commit_safe_reconciliation','reconcile_unadmitted','verify_terminal',
    'reconcile_completed_checkpoint','verify_cycle_binding','diagnose_attempt','apply_approved_configuration'))

class IssuerService(object):
    def __init__(self, store, host_readback, signer, issuer):
        need(isinstance(store,AuthorityStore) and callable(host_readback) and callable(signer),
             'TRUSTED_SERVICE_DEPENDENCIES')
        self.store,self.host_readback,self.signer,self.issuer=store,host_readback,signer,issuer
    def _host(self,grant,attempt,operation,payload):
        receipt=self.host_readback(grant,attempt,operation,payload)
        need(type(receipt) is dict and set(receipt)=={'grant_sha256','attempt_id',
            'operation','payload_sha256','run_id','job_id','invoke_id','backup_sha256',
            'checkpoint_sha256','log_sha256','result'},'HOST_RECEIPT_SCHEMA')
        need(receipt['grant_sha256']==digest(grant) and receipt['attempt_id']==attempt and
             receipt['operation']==operation and receipt['payload_sha256']==digest(payload),'HOST_RECEIPT_BINDING')
        for name in ('run_id','job_id','invoke_id'):
            need(type(receipt[name]) is str and 0<len(receipt[name])<=128,'TRANSACTION_IDS_UNKNOWN')
        for name in ('backup_sha256','checkpoint_sha256','log_sha256'):
            need(type(receipt[name]) is str and re.fullmatch('[0-9a-f]{64}',receipt[name]),'HOST_CHECKPOINT_UNKNOWN')
        need(type(receipt['result']) is dict,'HOST_RESULT')
        return receipt
    def handle(self,request,principal):
        """principal comes from authenticated transport metadata, never JSON input."""
        need(type(request) is dict and set(request)=={'schema','grant_sha256','attempt_id',
             'operation','nonce','payload'} and type(request['schema']) is int and request['schema']==1,
             'REQUEST_SCHEMA')
        need(type(request['nonce']) is str and re.fullmatch('[0-9a-f]{32}',request['nonce']) and
             type(request['attempt_id']) is str and bool(request['attempt_id']) and
             type(request['payload']) is dict and len(canonical(request))<=262144,'REQUEST_BOUND')
        need(type(principal) is dict and set(principal)=={'actor_id','host','writer_id'},'CHANNEL_PRINCIPAL')
        rows=self.store.db.execute('SELECT body FROM grants WHERE binding=?',(request['grant_sha256'],)).fetchall()
        need(len(rows)==1,'UNKNOWN_APPROVAL');grant=json.loads(rows[0][0])
        need(principal['actor_id']==grant['actor_id'] and principal['host']==grant['target_host'],
             'CHANNEL_SCOPE')
        attempt,operation,payload=request['attempt_id'],request['operation'],request['payload']
        # Revalidate/renew the same canonical writer lease for every request.
        # Actual phase effects still use the original independent install lock.
        token=(None if operation in ('read_committed_outcome','query_attempt_consumption') else self.store.lease(grant,principal['writer_id']))
        receipt=None
        result={'grant_id':grant['grant_id'],'attempt_id':attempt}
        if operation=='query_attempt_consumption':
            result.update(self.store.consumption(grant,attempt,payload));result['binding']=payload
        elif operation=='read_committed_outcome':
            committed=self.store.committed(grant,attempt)
            result.update(status='UNRESOLVED' if committed is None else 'COMMITTED_OUTCOME',
                          binding=payload,committed=committed)
        elif operation=='verify_fence':
            if attempt!='CANDIDATE':
                row=self.store.db.execute('SELECT state FROM attempts WHERE id=? AND grant_id=?',(attempt,grant['grant_id'])).fetchone()
                need(row is not None,'UNCLAIMED_ATTEMPT')
                need(row[0]=='UNKNOWN' or (row[0] in ('NO_WRITE','SAFE_CHECKPOINT') and
                     payload.get('step') in ('RECOVER_COMPLETE','RECONCILE','RECONCILE_UNADMITTED')),'CLOSED_ATTEMPT_EXECUTION')
            result.update(status='HELD',exclusive=True,writer=token['writer'],
                          lease_epoch=token['lease_epoch'],fence=token['fence'])
        elif operation=='consume_attempt':
            need(set(payload)=={'ordinal','command_sha256','ledger_sha256'},'CONSUME_BINDING')
            ordinal=self.store.consume(grant,attempt,payload['ordinal'],payload['command_sha256'],token,admission_payload=payload)
            result.update(status='CONSUMED',ordinal=ordinal,max_attempts=5)
        else:
            need(operation in HOST_OPERATIONS,'UNREVIEWED_OPERATION')
            row=self.store.db.execute('SELECT ordinal,state FROM attempts WHERE id=? AND grant_id=?',
                                     (attempt,grant['grant_id'])).fetchone()
            need(row is not None or (operation=='verify_cycle_binding' and attempt=='CANDIDATE'),'UNCLAIMED_ATTEMPT')
            cycle_operation=operation in ('verify_cycle_binding','diagnose_attempt','apply_approved_configuration')
            if cycle_operation:
                approved=self.store.cycle(grant,payload)
                if operation=='apply_approved_configuration':
                    need(payload.get('action') in approved['configuration_actions'],'UNAPPROVED_CONFIG')
                    need(row is not None and row[1]=='UNKNOWN','CONFIG_AFTER_RECONCILIATION_FORBIDDEN')
            receipt=self._host(grant,attempt,operation,payload)
            observed=receipt['result']
            need(observed.get('status') not in (None,'UNKNOWN'),'HOST_UNKNOWN')
            # Recheck the exact lease after host readback. An expired/stolen
            # lease cannot sign an admission, recovery or terminal response.
            self.store.transaction(lambda:self.store._fence(grant,token))
            if cycle_operation:
                need(observed.get('binding')==payload,'CYCLE_HOST_BINDING')
                if operation=='verify_cycle_binding':
                    identity={k:grant[k] for k in ('source_commit','source_tree','kit_sha256','manifest_sha256')}
                    if observed.get('source_identity')!=identity:
                        self.store.stop_cycle(grant,'SOURCE_CHANGE_NEW_PERMIT',token)
                    need(observed.get('source_identity')==identity and observed.get('status')=='UNCHANGED','SOURCE_CHANGE_NEW_PERMIT')
                if operation=='apply_approved_configuration':
                    action=payload['action']
                    need(observed.get('status')=='COMMITTED' and observed.get('action')==action and
                         receipt['checkpoint_sha256']==action['checkpoint_sha256'] and
                         observed.get('backup_sha256')==action['before_sha256'] and
                         observed.get('after_sha256')==action['after_sha256'],'CONFIG_RECEIPT_UNKNOWN')
                if operation=='diagnose_attempt':
                    identity={k:grant[k] for k in ('source_commit','source_tree','kit_sha256','manifest_sha256')}
                    if observed.get('source_identity')!=identity:
                        self.store.stop_cycle(grant,'SOURCE_CHANGE_NEW_PERMIT',token)
                    need(observed.get('source_identity')==identity,'SOURCE_CHANGE_NEW_PERMIT')
            if operation in ('commit_safe_reconciliation','reconcile_completed_checkpoint','reconcile_unadmitted','verify_terminal'):
                proof=observed.get('proof')
                need(type(proof) is dict and proof.get('outcome')==
                     ('SUCCESS' if operation=='verify_terminal' else
                      'NO_WRITE' if operation=='reconcile_unadmitted' else 'SAFE_CHECKPOINT'), 'TERMINAL_PROOF')
                self.store.reconcile(grant,attempt,proof['outcome'],digest(proof),token,
                                     lambda *unused:True,committed_receipt={'operation':operation,'payload':payload,
                                         'outcome':proof['outcome'],'result':observed,'host_receipt':receipt})
            result.update(observed)
        need(result.get('grant_id')==grant['grant_id'] and result.get('attempt_id')==attempt,'RESULT_SCOPE')
        now=int(self.store.clock())
        body={'schema':1,'issuer':self.issuer,'request_sha256':digest(request),
              'issued_utc':now,'expires_utc':min(now+30,grant['expires_utc']),'result':result}
        need(len(canonical(body))<=262144,'SIGNED_RESPONSE_BOUND')
        signature=self.signer(canonical(body))
        need(type(signature) is bytes and 256<=len(signature)<=512,'SIGNER_NOT_CONNECTED')
        # Service audit must commit before a signed response is returned.
        self.store.transaction(lambda:self.store.audit(grant['grant_id'],'SIGNED_RECEIPT',
                              {'attempt':attempt,'operation':operation,'body_sha256':digest(body),
                               'signed_body':body,'host_receipt':receipt}))
        return {'body':body,'signature':base64.b64encode(signature).decode('ascii')}
