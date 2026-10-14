"""Finite retained-certificate completion primitive; no standalone entrypoint.

Caller must hold the original install lock, consume one new exact approval,
verify epoch5 state and all writer-exclusion gates before apply. This helper
cannot grant admission and never invokes certonly or production force-renewal.
"""
import copy,hashlib,json,os
import p2_tls_lifecycle as tls
from p2_bootstrap_files import private_read
from ledger_cutover_transaction import _atomic_receipt
OLD_JOURNAL_SHA='8bdd9e5a40a21980f342ca0c2c98e2c5efffd7543e981855ad4481f63e5b7c14'
CERT_SHA='f7caaaed2c24582a22df2f4708e8140a8f27007d64f1dd9436ce972e145fc6f6'
OLD_RELEASE='338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09'

def need(value,label):
 if not value:raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def preserve_exact(path,raw):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 parent=os.open(os.path.dirname(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(parent)
 finally:os.close(parent)

class RetainedCertificateLifecycle(tls.TlsLifecycle):
 def prepared_inputs(self,ref):
  self.authority()
  need(isinstance(ref,dict) and set(ref)=={'path','sha256'},'EPOCH5_TLS_REFERENCE')
  new_raw=private_read(ref['path']);need(sha(new_raw)==ref['sha256'],'EPOCH5_TLS_CONFIG_HASH')
  new=tls.validate(json.loads(new_raw.decode()))
  old_raw=private_read(self.journal);need(sha(old_raw)==OLD_JOURNAL_SHA,'EPOCH5_TLS_OLD_JOURNAL_CHANGED')
  old=json.loads(old_raw.decode());tls.validate(old['config'])
  need(old['state']=='HOLD' and old['certificate_sha256']==CERT_SHA,'EPOCH5_TLS_ISSUED_HOLD_REQUIRED')
  need(old['config']['release_sha256']==OLD_RELEASE and new['release_sha256']!=OLD_RELEASE,'EPOCH5_TLS_RELEASE_TRANSITION')
  need(all(new[k]==old['config'][k] for k in new if k!='release_sha256'),'EPOCH5_TLS_IDENTITY_CHANGED')
  need(old['fingerprint']==tls.fingerprint(tls.ROOT),'EPOCH5_TLS_RETAINED_TREE_CHANGED')
  tls.client_config()
  backup=self.directory+'/epoch5-prior-tls-lifecycle.json'
  need(not os.path.lexists(backup),'EPOCH5_TLS_ALREADY_ATTEMPTED')
  return new,old,old_raw,backup
 def prepare(self,ref):return self.prepared_inputs(ref)[0]
 def apply(self,ref):
  new,old,old_raw,backup=self.prepared_inputs(ref)
  preserve_exact(backup,old_raw)
  # The outer one-shot attempt is already consumed before entering this helper.
  record=copy.deepcopy(old);record.update(config=new,state='REQUESTED',prior_journal_sha256=OLD_JOURNAL_SHA,issuance_replayed=False)
  _atomic_receipt(self.journal,record)
  try:
   need(tls.certificate_check()==CERT_SHA,'EPOCH5_RETAINED_CERTIFICATE_CHANGED')
   tls.available_port()
   renewal=tls.ROOT+'/config/renewal/'+tls.DOMAIN+'.conf'
   need(os.path.realpath(renewal)==renewal and os.path.isfile(renewal),'EPOCH5_TLS_RENEWAL_CONFIG')
   tls.command(tls.base_args()+tls.renewal_args(dry_run=True),timeout=240)
   need(tls.certificate_check()==CERT_SHA,'EPOCH5_DRYRUN_REPLACED_CERTIFICATE')
   record['state']='READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED'
   record['certificate_sha256']=CERT_SHA
  except BaseException:
   record['state']='HOLD';raise
  finally:
   record['fingerprint']=tls.fingerprint(tls.ROOT);_atomic_receipt(self.journal,record)
  return record
