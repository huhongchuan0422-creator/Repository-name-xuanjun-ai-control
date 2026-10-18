"""Bounded data-only JSON configuration CAS, with durable original backup.

An administrator maps approved action IDs to dedicated configuration files.
Neither target paths nor executable commands come from the client. The caller
must hold the canonical transaction lock and supply the real fence validator.
This helper is not an installer and cannot edit arbitrary source files.
"""
import hashlib
import json
import os
import stat
from receipt_provider import need, canonical, digest

def sha(value):return hashlib.sha256(value).hexdigest()

class ApprovedConfiguration(object):
    def __init__(self, directory, actions, fence, checkpoint):
        need(os.path.isabs(directory) and os.path.normpath(directory)==directory and callable(fence) and callable(checkpoint),'CONFIG_ROOT')
        current='/'
        for part in directory.split('/')[1:]:
            current=os.path.join(current,part);info=os.lstat(current)
            need(stat.S_ISDIR(info.st_mode) and not info.st_mode&0o022,'CONFIG_ANCESTRY')
        info=os.lstat(directory)
        need(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,'CONFIG_OWNER')
        self.directory=directory
        self.fd=os.open(directory,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
        self.actions=dict(actions);self.fence=fence;self.checkpoint=checkpoint
    def close(self):os.close(self.fd)
    def read(self,name):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.fd)
        try:
            info=os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.geteuid() and
                 stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=65536,'CONFIG_FILE')
            value=os.read(fd,65537);need(len(value)<=65536,'CONFIG_BOUND')
            json.loads(value.decode('utf-8'))
            return value,(info.st_dev,info.st_ino)
        finally:os.close(fd)
    def create(self,name,value):
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        try:
            view=memoryview(value)
            while view:
                count=os.write(fd,view);need(count>0,'CONFIG_WRITE');view=view[count:]
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(self.fd)
    def apply(self,action):
        need(action['id'] in self.actions,'UNAPPROVED_CONFIG')
        name,payload=self.actions[action['id']]
        need(action.get('target')==os.path.join(self.directory,name),'CONFIG_TARGET_BINDING')
        need(type(name) is str and name.endswith('.json') and '/' not in name and not name.startswith('.'),'CONFIG_DATA_ONLY')
        need(type(payload) is bytes and len(payload)<=65536 and sha(payload)==action['payload_sha256'] and
             sha(payload)==action['after_sha256'],'CONFIG_PAYLOAD_BINDING')
        need(type(json.loads(payload.decode('utf-8'))) is dict,'CONFIG_JSON_OBJECT')
        tag=digest(action)
        backup='backup-'+tag+'.json';intent='intent-'+tag+'.json';temp='pending-'+tag+'.json'
        self.fence()
        need(self.checkpoint()==action['checkpoint_sha256'],'CONFIG_CHECKPOINT_UNKNOWN')
        before,identity=self.read(name)
        if sha(before)==action['after_sha256']:
            original,_=self.read(backup);record,_=self.read(intent)
            need(sha(original)==action['before_sha256'] and record==canonical(action),'CONFIG_REPLAY_UNPROVEN')
            return {'status':'COMMITTED','action':action,'backup_sha256':sha(original),'after_sha256':sha(before)}
        need(sha(before)==action['before_sha256'],'CONFIG_CONCURRENT_CHANGE')
        # Existing partial output is preserved and must be reconciled first.
        self.create(backup,before)
        self.create(intent,canonical(action))
        self.create(temp,payload)
        self.fence()
        current,now=self.read(name)
        need(current==before and now==identity,'CONFIG_CAS_CONFLICT')
        os.replace(temp,name,src_dir_fd=self.fd,dst_dir_fd=self.fd);os.fsync(self.fd)
        observed,_=self.read(name)
        need(observed==payload,'CONFIG_READBACK')
        return {'status':'COMMITTED','action':action,'backup_sha256':sha(before),'after_sha256':sha(observed)}
