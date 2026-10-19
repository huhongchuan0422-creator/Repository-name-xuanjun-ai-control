"""P2-only management policy, reconciliation and real signing adapter.

Uses the existing Provider reservation journal. No AuthorityStore creation,
cloud credential changes, key generation, directory discovery or Writer start.
External isolation facts require independently signed, fresh original evidence.
"""
import base64
import json
import os
import sqlite3
import stat
import subprocess
import time
from urllib.parse import quote

r = None
e = None


def signing_key(ref, public):
    r.reference(ref)
    fd=r.opened(ref['path'])
    try:
        # Hash the exact protected file and sign through the same descriptor.
        raw=os.read(fd,16385)
        r.need(len(raw)<=16384 and r.sha(raw)==ref['sha256'],'SIGNER_FILE_SHA')
        os.lseek(fd,0,0)
        der=subprocess.check_output(['/usr/bin/openssl','pkey','-in','/proc/self/fd/'+str(fd),
            '-pubout','-outform','DER'],pass_fds=(fd,),stderr=subprocess.DEVNULL,timeout=3)
        expected=r.openssl(['pkey','-pubin','-outform','DER'],public)
        r.need(der==expected,'CONTROL_SIGNER_TRUST')
        return fd
    except BaseException:
        os.close(fd);raise


def sign(body, refs, keys):
    r.need(type(refs) is dict and set(refs)==r.ROLES,'CONTROL_SIGNERS')
    out={}
    for role in sorted(r.ROLES):
        fd=signing_key(refs[role],keys[role])
        try:
            os.lseek(fd,0,0)
            raw=subprocess.check_output(['/usr/bin/openssl','dgst','-sha256','-sign',
                '/proc/self/fd/'+str(fd)],input=r.canonical(body),pass_fds=(fd,),
                stderr=subprocess.DEVNULL,timeout=3)
        finally:os.close(fd)
        out[role]=base64.b64encode(raw).decode('ascii')
        r.signature(body,out[role],keys[role])
    return out


def transaction_snapshot(ref):
    """Read an already consistent manager-created backup, never a live store."""
    r.inspect_snapshot(ref)  # Exact SHA, safe copy, integrity/schema/attempt rules.
    raw=r.read(ref['path'],ref['sha256'],16777216)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='p2-control-snapshot-',dir='/root') as root:
        name=root+'/snapshot.sqlite3'
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        db=sqlite3.connect('file:'+quote(name,safe='/')+'?mode=ro&immutable=1',uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            grants=db.execute('SELECT id,consumed,terminal FROM grants ORDER BY id LIMIT 10001').fetchall()
            attempts=db.execute('SELECT id,grant_id,ordinal,state,proof FROM attempts ORDER BY grant_id,ordinal LIMIT 10001').fetchall()
            audit=db.execute('SELECT id,grant_id,event,body FROM audit ORDER BY id LIMIT 10001').fetchall()
            r.need(max(len(grants),len(attempts),len(audit))<=10000,'CONTROL_HISTORY_BOUND')
            return {'snapshot_sha256':ref['sha256'],'grants':grants,'attempts':attempts,
                    'audit_sha256':r.sha(r.canonical(audit)),'audit_count':len(audit)}
        finally:db.close()


def invocation_state(rpc, invoke_id):
    """Reuse real existing SWAS RPC; QUERY ONLY, never sends RunCommand."""
    r.ident(invoke_id)
    value=rpc('swas.eu-west-1.aliyuncs.com','DescribeInvocationResult',RegionId='eu-west-1',
              InstanceId='40dfc6a47d5e4363b9da7d0d6ab01cb1',InvokeId=invoke_id)
    r.need(type(value) is dict,'CLOUD_QUERY_UNKNOWN')
    detail=value.get('InvocationResult')
    # Same concrete Invocation shape accepted by the existing SWAS transport.
    r.need(type(detail) is dict and detail.get('InvokeId')==invoke_id and
           detail.get('InstanceId')=='40dfc6a47d5e4363b9da7d0d6ab01cb1','CLOUD_QUERY_BINDING')
    status=detail.get('InvocationStatus')
    r.need(status in ('Success','Failed','Timeout','Cancelled','Pending','Running','Stopping'), 'CLOUD_QUERY_UNKNOWN')
    # Even Success proves only command transport termination, NOT side-effect reconciliation.
    return {'invoke_id':invoke_id,'transport_status':status,
            'effects':'REQUIRES_TRANSACTION_RECEIPT','terminal':status in ('Success','Failed','Timeout','Cancelled')}


class ControlPlane(object):
    def __init__(self,journal,request,keys,plan_ref,restoration,config_ref):
        self.journal,self.request,self.keys=journal,request,keys
        self.plan_ref,self.restoration=plan_ref,restoration
        self.ref=r.reference(config_ref)
        self.cfg=r.decode(r.read(config_ref['path'],config_ref['sha256']))
        cfg=self.cfg
        r.fields(cfg,'schema host request_sha256 trust signing_keys plan_sha256 live_evidence_path inventory invoke_receipts snapshot')
        r.need(type(cfg['schema']) is int and cfg['schema']==1 and cfg['host']==r.HOST and
               cfg['request_sha256']==r.sha(r.canonical(request)), 'CONTROL_CONFIG_SCOPE')
        r.reference(cfg['trust'])
        registered=r.load_trust(cfg['trust']['path'],cfg['trust']['sha256'])
        r.need(registered==keys,'CONTROL_TRUST_BINDING')
        r.need(type(cfg['signing_keys']) is dict and set(cfg['signing_keys'])==r.ROLES,'CONTROL_SIGNERS')
        for role,ref in cfg['signing_keys'].items():r.reference(ref)
        r.reference(cfg['inventory']);r.path(cfg['live_evidence_path'])
        r.need(r.pin(cfg['plan_sha256'])==plan_ref['sha256'],'CONTROL_PLAN_BINDING')
        r.need(type(cfg['invoke_receipts']) is list and len(cfg['invoke_receipts'])<=100,'INVOKE_BOUND')
        for ref in cfg['invoke_receipts']:r.reference(ref)
        if cfg['snapshot'] is not None:r.reference(cfg['snapshot'])

    def register(self, approval_ref):
        # Owner-signed exact public/private source references; no secret contents in audit.
        r.reference(approval_ref)
        approval=r.decode(r.read(approval_ref['path'],approval_ref['sha256']))
        r.fields(approval,'config_sha256 signature')
        r.need(approval['config_sha256']==self.ref['sha256'],'CONTROL_APPROVAL_BINDING')
        r.signature({'config_sha256':approval['config_sha256']},approval['signature'],self.keys['owner'])
        # Enroll only the local deny policy. Admission still requires facts() on
        # every query; do not require isolation success to install its deny gate.
        db=self.journal.db
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('CREATE TABLE IF NOT EXISTS control_config(request_sha TEXT PRIMARY KEY,config_sha TEXT NOT NULL,trust_sha TEXT NOT NULL,approval TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS revoked_authorities(authority_id TEXT PRIMARY KEY,through_epoch INTEGER NOT NULL,request_sha TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS channel_revocations(request_sha TEXT NOT NULL,channel TEXT NOT NULL,inventory_sha TEXT NOT NULL,PRIMARY KEY(request_sha,channel))')
            row=db.execute('SELECT config_sha,trust_sha,approval FROM control_config WHERE request_sha=?',
                           (self.cfg['request_sha256'],)).fetchone()
            expected=(self.ref['sha256'],self.cfg['trust']['sha256'],r.canonical(approval_ref).decode('ascii'))
            r.need(row is None or row==expected,'CONTROL_CONFIG_ALREADY_BOUND')
            if row is None:db.execute('INSERT INTO control_config VALUES(?,?,?,?)',(self.cfg['request_sha256'],)+expected)
            old=db.execute('SELECT through_epoch,request_sha FROM revoked_authorities WHERE authority_id=?',
                           (self.request['old_authority_id'],)).fetchone()
            expected_old=(self.request['old_epoch'],self.cfg['request_sha256'])
            r.need(old is None or old==expected_old,'OLD_EPOCH_CONFLICT')
            if old is None:db.execute('INSERT INTO revoked_authorities VALUES(?,?,?)',
                (self.request['old_authority_id'],)+expected_old)
            for channel in sorted(r.CHANNELS):
                db.execute('INSERT OR IGNORE INTO channel_revocations VALUES(?,?,?)',
                           (self.cfg['request_sha256'],channel,self.cfg['inventory']['sha256']))
            os.fsync(self.journal.parent)
            # SQLite FULL commit is final publication, as in the accepted Registry.
            db.commit()
        except BaseException:
            if db.in_transaction:db.rollback()
            raise

    def registered(self):
        info=os.stat(os.path.basename(self.journal.path),dir_fd=self.journal.parent,follow_symlinks=False)
        r.need((info.st_dev,info.st_ino)==(self.journal.identity.st_dev,self.journal.identity.st_ino),
               'CONTROL_JOURNAL_REPLACED')
        r.need(r.sha(r.read(self.ref['path']))==self.ref['sha256'],'CONTROL_CONFIG_CHANGED')
        try:
            row=self.journal.db.execute('SELECT config_sha,trust_sha,approval FROM control_config WHERE request_sha=?',
                                       (self.cfg['request_sha256'],)).fetchone()
        except sqlite3.Error:raise r.Hold('CONTROL_NOT_REGISTERED')
        r.need(row is not None and row[:2]==(self.ref['sha256'],self.cfg['trust']['sha256']),'CONTROL_NOT_REGISTERED')
        approval_ref=r.decode(row[2].encode('ascii'));r.reference(approval_ref)
        approval=r.decode(r.read(approval_ref['path'],approval_ref['sha256']))
        r.fields(approval,'config_sha256 signature')
        r.need(approval['config_sha256']==self.ref['sha256'],'CONTROL_APPROVAL_BINDING')
        r.signature({'config_sha256':approval['config_sha256']},approval['signature'],self.keys['owner'])

    def enforce(self,authority_id,epoch,writer_id,grant_id):
        self.registered()
        r.need(type(epoch) is int,'CONTROL_EPOCH')
        row=self.journal.db.execute('SELECT through_epoch FROM revoked_authorities WHERE authority_id=?',
                                   (authority_id,)).fetchone()
        r.need(row is None or epoch>row[0],'OLD_EPOCH_REVOKED')
        q=self.request
        r.need((authority_id,epoch,writer_id,grant_id)==
               (q['new_authority_id'],q['new_epoch'],q['writer_id'],q['new_grant_id']), 'CONTROL_FENCE_CONFLICT')

    def status(self):
        self.registered()
        row=self.journal.db.execute('SELECT through_epoch FROM revoked_authorities WHERE authority_id=?',
                                   (self.request['old_authority_id'],)).fetchone()
        return {'schema':1,'request_sha256':self.cfg['request_sha256'],
                'config_sha256':self.ref['sha256'],'trust_sha256':self.cfg['trust']['sha256'],
                'local_old_epoch_deny_enrolled':row==(self.request['old_epoch'],),
                'production_admission':'NOT_EVALUATED','external_isolation':'NOT_INFERRED',
                'authority_initialized':False,'writer_started':False}

    def facts(self):
        # Owner binds the protected live source path once. Each replacement must
        # authenticate all three signatures and current expiry; no retry approval.
        packet=r.decode(r.read(self.cfg['live_evidence_path']))
        r.decide(self.request,packet,self.keys)
        r.need(self.plan_ref in packet['body']['sources'],'CONTROL_PLAN_NOT_SIGNED')
        if self.restoration is not None:
            r.need(r.canonical(packet['body']['restoration'])==r.canonical(self.restoration),'CONTROL_RESTORATION')
        inventory_refs=[ref for ref in packet['body']['sources'] if ref['path']==self.cfg['inventory']['path']]
        r.need(len(inventory_refs)==1,'CONTROL_INVENTORY_SOURCE')
        inventory_ref=inventory_refs[0]
        inventory=r.decode(r.read(inventory_ref['path'],inventory_ref['sha256']))
        r.fields(inventory,'schema request_sha256 channels invoke_ids signatures')
        signed={k:v for k,v in inventory.items() if k!='signatures'}
        r.need(type(inventory['schema']) is int and inventory['schema']==1 and
               inventory['request_sha256']==self.cfg['request_sha256'] and
               type(inventory['channels']) is dict and set(inventory['channels'])==r.CHANNELS and
               type(inventory['signatures']) is dict and set(inventory['signatures'])==r.ROLES,'CONTROL_INVENTORY')
        for role in sorted(r.ROLES):r.signature(signed,inventory['signatures'][role],self.keys[role])
        r.need(inventory_ref in packet['body']['sources'],'CONTROL_INVENTORY_NOT_SIGNED')
        for kind,channel in inventory['channels'].items():
            r.fields(channel,'status principals enforcement')
            r.need(channel['status'] in ('ISOLATED','NOT_PRESENT_PROVEN') and
                   type(channel['principals']) is list and len(channel['principals'])<=100,'EXTERNAL_WRITER_UNKNOWN')
            for principal in channel['principals']:r.ident(principal)
            r.need(len(set(channel['principals']))==len(channel['principals']) and
                   (channel['status']!='NOT_PRESENT_PROVEN' or channel['principals']==[]) and
                   channel['status']==packet['body']['inventory']['channels'][kind]['status'],
                   'CHANNEL_INVENTORY_CONFLICT')
            r.reference(channel['enforcement'])
            r.read(channel['enforcement']['path'],channel['enforcement']['sha256'])
            r.need(channel['enforcement'] in packet['body']['sources'] and
                   packet['body']['inventory']['channels'][kind]['receipt_sha256']==channel['enforcement']['sha256'],
                   'ENFORCEMENT_NOT_BOUND')
        r.need(type(inventory['invoke_ids']) is list and all(type(x) is str for x in inventory['invoke_ids']) and len(set(inventory['invoke_ids']))==len(inventory['invoke_ids']), 'INVOKE_INVENTORY')
        seen=set()
        for ref in self.cfg['invoke_receipts']:
            value=r.decode(r.read(ref['path'],ref['sha256']))
            r.fields(value,'body signatures')
            body=value['body'];r.fields(body,'request_sha256 invoke_id terminal effects transaction_sha256')
            r.need(type(value['signatures']) is dict and set(value['signatures'])==r.ROLES,'INVOKE_SIGNATURES')
            for role in sorted(r.ROLES):r.signature(body,value['signatures'][role],self.keys[role])
            r.need(body['request_sha256']==self.cfg['request_sha256'] and body['terminal'] is True and
                   body['effects']=='RECONCILED' and body['invoke_id'] not in seen,'INVOKE_UNKNOWN')
            r.ident(body['invoke_id']);r.pin(body['transaction_sha256'])
            r.need(any(source['sha256']==body['transaction_sha256'] for source in packet['body']['sources']),
                   'INVOKE_TRANSACTION_SOURCE_MISSING')
            r.need(ref in packet['body']['sources'],'INVOKE_NOT_SIGNED')
            seen.add(body['invoke_id'])
        r.need(seen==set(inventory['invoke_ids']),'INVOKE_CLOSURE_INCOMPLETE')
        if self.cfg['snapshot'] is not None:
            r.need(self.cfg['snapshot'] in packet['body']['sources'],'SNAPSHOT_NOT_SIGNED')
            transaction_snapshot(self.cfg['snapshot'])
        elif self.request['route']=='RESTORE_EXISTING':raise r.Hold('CONTROL_SNAPSHOT_REQUIRED')
        return packet

    def respond(self,probe):
        self.registered()
        q=self.request
        self.journal.check(q,probe['operation'])
        self.enforce(q['new_authority_id'],q['new_epoch'],q['writer_id'],q['new_grant_id'])
        packet=self.facts()
        now=int(time.time())
        reservation={'old_authority_id':q['old_authority_id'],'authority_id':q['new_authority_id'],
            'epoch':q['new_epoch'],'fence':q['new_epoch'],'writer_id':q['writer_id'],
            'grant_id':q['new_grant_id'],'database':q['target_database'],
            'plan_sha256':self.plan_ref['sha256'],'exclusive':True}
        body={'schema':1,'probe':probe,'issued_utc':now,
            'expires_utc':min(now+20,packet['body']['expires_utc']),'packet':packet,'reservation':reservation}
        response={'body':body,'signatures':sign(body,self.cfg['signing_keys'],self.keys)}
        e.validate_response(q,probe,response,self.keys,self.plan_ref,self.restoration)
        # Exclusive claim is durable before releasing even a signed response.
        self.journal.commit(q,response,probe['operation'])
        return response
