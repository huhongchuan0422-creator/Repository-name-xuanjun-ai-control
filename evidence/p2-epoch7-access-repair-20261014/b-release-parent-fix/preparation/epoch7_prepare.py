#!/usr/bin/env python3
"""Artifact-bound R7 fresh preparation candidate. Never installs, probes or resumes.

This preserves every previously published candidate. Only exact existing host files are
read. Complete private outputs are created exclusively after every compiler and
the independent topology review authenticate. Missing review leaves no outputs.
"""
import argparse
import contextlib
import copy
import errno
import hashlib
import importlib
import json
import os
import re
import signal
import stat
import sys
import time
import types

BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
CAND = BASE+'/complete-install-candidate-38503014520'
PINS_BOUND = True
KIT_ROOT = CAND+'/epoch7-recovery-candidate-r7'
PREP_ROOT = CAND+'/epoch7-preparation-candidate-r7-fresh-parent'
# Original saved-evidence kit stays immutable. The independent compiler artifact
# must be published and reviewed before these fixed pins can be bound.
COMPILER_KIT_ROOT = CAND+'/epoch7-recovery-candidate-r7-parentfix'
COMPILER_KIT_SHA = None
COMPILER_ENTRY_SHA = None
RELEASE_PARENT = '/opt/xuanjun-control-releases'
KIT_SHA = '7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
ENTRY_SHA = '1be06802e012b5747f837af02ff8746fec9864ef94715b561f67c39be95e0948'
# Frozen candidate dependencies. These pins are not command-line authority.
# The separate wrapper itself must be authenticated by the delivery command.
PREPARATION_SOURCES = {
    'epoch7_prepare_data':'71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1',
    'epoch7_topology_projection':'0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6'}
# Accepted saved evidence has its own immutable source provenance. The wrapper
# is separately delivery-pinned; its own manifest must never replace this one.
SAVED_PROJECTION_SOURCES = {'schema':2,'kind':'R7_SAVED_PROJECTION_PURE_SOURCES','files':{
    'epoch7_prepare_data.py':PREPARATION_SOURCES['epoch7_prepare_data'],
    'epoch7_topology_projection.py':PREPARATION_SOURCES['epoch7_topology_projection'],
    'export_schema.py':'df216347c7e969942be4e8eea42dfe580b3b155ff4a36d1383e9bca0cf253629'}}
SAVED_PROJECTION_MANIFEST_SHA = '311c5150f628c0232298bc62d233d2eccf26681d1d0fdfa379b4cab8d242f1d3'
EXPECTED_REVIEW_BODY_SHA = '37ee583dfda581361caf38e8cccf5ffb9b25f28c8f732e17e0cbf6e72982c9b7'
OBSERVATION_PATH = CAND+'/epoch7-observation-8df3b22b3762070f.private.json'
OBSERVATION_SHA = 'a3f7042a1b3099c5699aaef547b22c8f744f0bdc514043a2a91a9847639f4f68'
HOST = 'iZd7oeikknn1z21sq6ji6zZ' 
SHA = re.compile(r'^[0-9a-f]{64}$')
MAX_TOTAL = 128*1024*1024
MAX_FILES = 512
SECONDS = 120
STATUS_SECONDS = 5
PHASES = frozenset(('INPUT_VALIDATION','BOOTSTRAP','VERIFY_KIT','LOAD_PREPARATION_SOURCES',
    'VERIFY_COMPILER_KIT','COLLECT_INPUTS','FRESH_RELEASE_PARENT','FRESH_UNIT_AUTHORITY','PROJECT_TOPOLOGY','FETCH_TOPOLOGY_REVIEW','COMPILE_PRIVATE_BUNDLE',
    'VERIFY_BEFORE_PUBLICATION','PUBLISH_OUTPUTS','VERIFY_AFTER_PUBLICATION',
    'FINALIZE_BUDGET','DELIVER_STATUS'))
CURRENT_PHASE = 'INPUT_VALIDATION'
# Explicit source-defined labels only. Unknown cached-helper messages are never
# echoed. This intentionally does not authorize a prefix/substring fallback.
SAFE_FAILURE_LABELS = frozenset(('EPOCH7_PREP_ARGUMENTS','EPOCH7_PREP_DEADLINE',
    'EPOCH7_PREP_R7_ARTIFACT_UNBOUND','EPOCH7_PREP_COMPILER_ARTIFACT_UNBOUND',
    'EPOCH7_PREP_RELEASE_PARENT_BINDING','EPOCH7_PREP_RELEASE_PARENT_AUTHORITY',
    'EPOCH7_PREP_RELEASE_PARENT_ANCESTOR_POLICY','EPOCH7_PREP_RELEASE_PARENT_REPEAT_DRIFT',
    'EPOCH7_PREP_RELEASE_PARENT_SCOPE','EPOCH7_PREP_COMPILER_RUNTIME_CHANGED',
    'EPOCH7_PREP_COMPILER_KIT_FINAL_CHANGED','EPOCH7_PREP_COMPILER_KIT_POST_PUBLICATION_CHANGED',
    'EPOCH7_PREP_SOURCE_FREEZE_REQUIRED','EPOCH7_PREP_PREPARATION_SOURCE_PIN',
    'EPOCH7_PREP_ORIGINAL_PLAN_PIN','EPOCH7_PREP_PACKAGE_MANIFEST_PIN',
    'EPOCH7_PREP_HISTORICAL_KIT_SCOPE','EPOCH7_PREP_HISTORICAL_HELPER_PIN',
    'EPOCH7_PREP_SOURCE_BYTES_PIN','EPOCH7_PREP_REPRODUCED_V4_PLAN_PIN',
    'EPOCH7_PREP_COMPLETE_OBSERVATION_REQUIRED','EPOCH7_PREP_OBSERVATION_RETAINED_BINDING',
    'EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY','EPOCH7_PREP_MANAGER_OBSERVATION_BINDING',
    'EPOCH7_PREP_TOOL_OBSERVATION_BINDING',
    'EPOCH7_PREP_RETAINED_BUFFER_CHANGED','EPOCH7_PREP_GATHER_OBSERVATION_DRIFT',
    'EPOCH7_PREP_OUTPUT_EXISTS','EPOCH7_PREP_ALL_OUTPUT_BOUNDS',
    'EPOCH7_PREP_OUTPUT_UNOWNED_DIRECTORY_CHANGE','EPOCH7_PREP_KIT_FINAL_CHANGED',
    'EPOCH7_PREP_KIT_POST_PUBLICATION_CHANGED','EPOCH7_PREP_PREPARATION_UNRESOLVED',
    'EPOCH7_PREP_GENUINE_REVIEW_AND_EXPLICIT_TIMER_REQUIRED',
    'EPOCH7_PREP_SAVED_SOURCE_MANIFEST_PIN','EPOCH7_PREP_ACCEPTED_REVIEW_BODY_PIN',
    'EPOCH7_PREP_FIXED_R7_OBSERVATION','EPOCH7_PREP_FRESH_DROPIN_PRESENCE',
    'EPOCH7_PREP_FRESH_DROPIN_FILE_SET','EPOCH7_PREP_FRESH_DROPIN_FIELDS',
    'EPOCH7_PREP_FRESH_DROPIN_REPEAT_DRIFT','EPOCH7_PREP_FRESH_DROPIN_RACE',
    'EPOCH7_PREP_FRESH_DROPIN_DIRECTORY_TYPE','EPOCH7_PREP_FRESH_DROPIN_PARENT_RACE',
    'EPOCH7_PREP_FRESH_DROPIN_SAVED_BINDING'))


def phase(name):
    global CURRENT_PHASE
    if name not in PHASES:raise ValueError('EPOCH7_PREP_PHASE')
    CURRENT_PHASE=name


def need(ok, label):
    if not ok: raise ValueError('EPOCH7_PREP_'+label)


def require_binding():
    need(PINS_BOUND is True and type(KIT_SHA) is str and SHA.fullmatch(KIT_SHA) and
         type(ENTRY_SHA) is str and SHA.fullmatch(ENTRY_SHA), 'R7_ARTIFACT_UNBOUND')
    need(sha(packed(SAVED_PROJECTION_SOURCES)[:-1])==SAVED_PROJECTION_MANIFEST_SHA and
         all(SAVED_PROJECTION_SOURCES['files'][name+'.py']==pin for name,pin in PREPARATION_SOURCES.items()),
         'SAVED_SOURCE_MANIFEST_PIN')


def require_compiler_binding():
    need(COMPILER_KIT_ROOT==CAND+'/epoch7-recovery-candidate-r7-parentfix' and
         COMPILER_KIT_ROOT!=KIT_ROOT and type(COMPILER_KIT_SHA) is str and SHA.fullmatch(COMPILER_KIT_SHA) and
         type(COMPILER_ENTRY_SHA) is str and SHA.fullmatch(COMPILER_ENTRY_SHA), 'COMPILER_ARTIFACT_UNBOUND')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def packed(value): return json.dumps(value,sort_keys=True,separators=(',', ':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
def stamps(info):
    return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
        'mode':stat.S_IMODE(info.st_mode),'nlink':info.st_nlink,'size':info.st_size,
        'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}


class DeadlineError(Exception): pass
class CleanupError(Exception): pass
class StatusDeliveryError(Exception): pass


@contextlib.contextmanager
def budget(seconds=SECONDS):
    need(type(seconds) in (int,float) and 0 < seconds <= SECONDS, 'BUDGET')
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0), 'EXISTING_ALARM')
    end=time.monotonic()+seconds;old=signal.getsignal(signal.SIGALRM);primary=None
    def expired(unused_signum,unused_frame): raise DeadlineError()
    try:
        signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,seconds,.1)
        yield end
        need(time.monotonic()<end,'DEADLINE')
    except BaseException as error:
        primary=error;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,old)
        except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.preparation_cleanup_failed=True


def load_entry(raw,compiler=False):
    need(type(compiler) is bool,'COMPILER_ARTIFACT_UNBOUND')
    if compiler:require_compiler_binding()
    root,pin=(COMPILER_KIT_ROOT,COMPILER_ENTRY_SHA) if compiler else (KIT_ROOT,ENTRY_SHA)
    need(type(raw) is bytes and len(raw)<=1024*1024 and sha(raw)==pin,'ENTRY_PIN')
    module=types.ModuleType('epoch7_preparation_compiler_entry' if compiler else 'epoch7_preparation_r7_entry')
    module.__file__=root+'/epoch7_recovery_entry.py'
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module


def bootstrap_entry(compiler=False):
    """Authenticate one of the two fixed entries before importing its reader."""
    require_binding();need(type(compiler) is bool,'COMPILER_ARTIFACT_UNBOUND')
    if compiler:require_compiler_binding()
    path=(COMPILER_KIT_ROOT if compiler else KIT_ROOT)+'/epoch7_recovery_entry.py';parts=path[1:].split('/');held=[];links=[];primary=None
    try:
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);held.append(fd)
        def authority(value):
            info=os.fstat(value);need(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and
                not info.st_mode&0o7022,'BOOTSTRAP_ANCESTRY');no_attributes(value);return stamps(info)
        roots=[(fd,authority(fd))]
        for part in parts[:-1]:
            parent=fd;before=os.stat(part,dir_fd=parent,follow_symlinks=False)
            fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(fd)
            row=authority(fd);need(row==stamps(before),'BOOTSTRAP_DIRECTORY_RACE');roots.append((fd,row));links.append((parent,part,row))
        before=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)
        leaf=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd);held.append(leaf)
        info=os.fstat(leaf);need(stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0 and
            info.st_nlink==1 and not info.st_mode&0o7022 and 0<info.st_size<=1024*1024 and stamps(before)==stamps(info),
            'BOOTSTRAP_ENTRY_AUTHORITY');no_attributes(leaf)
        chunks=[];count=0
        while True:
            part=os.read(leaf,min(65536,1024*1024+1-count))
            if not part:break
            count+=len(part);need(count<=1024*1024,'BOOTSTRAP_ENTRY_BOUND');chunks.append(part)
        raw=b''.join(chunks);no_attributes(leaf)
        need(count==info.st_size and stamps(os.fstat(leaf))==stamps(info)==stamps(os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)),
             'BOOTSTRAP_ENTRY_RACE')
        for parent,name,row in links:need(stamps(os.stat(name,dir_fd=parent,follow_symlinks=False))==row,'BOOTSTRAP_PATH_RACE')
        for value,row in roots:need(authority(value)==row,'BOOTSTRAP_ANCESTRY_RACE')
        return load_entry(raw,compiler)
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        for fd in reversed(held):
            try:os.close(fd)
            except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.preparation_cleanup_failed=True


def preparation_sources(gather):
    need(all(type(value) is str and SHA.fullmatch(value) for value in PREPARATION_SOURCES.values()),'SOURCE_FREEZE_REQUIRED')
    need(os.path.abspath(__file__)==PREP_ROOT+'/epoch7_prepare.py','EXACT_PREPARATION_LOCATION')
    own=gather.read(PREP_ROOT+'/epoch7_prepare.py',1024*1024)[0]
    cache={}
    for name,pin in PREPARATION_SOURCES.items():
        raw=gather.read(PREP_ROOT+'/'+name+'.py',262144)[0]
        need(sha(raw)==pin,'PREPARATION_SOURCE_PIN');cache[name]=raw
    manifest={'schema':1,'files':dict({name+'.py':sha(raw) for name,raw in cache.items()},
                                      **{'epoch7_prepare.py':sha(own)})}
    return cache,manifest


@contextlib.contextmanager
def preparation_modules(cache):
    need(set(cache)==set(PREPARATION_SOURCES) and not set(cache)&set(sys.modules),'PREPARATION_MODULE_SCOPE')
    modules={}
    try:
        for name in ('epoch7_prepare_data','epoch7_topology_projection'):
            raw=cache[name];need(sha(raw)==PREPARATION_SOURCES[name],'PREPARATION_SOURCE_PIN')
            module=types.ModuleType(name);module.__file__=PREP_ROOT+'/'+name+'.py'
            exec(compile(raw,module.__file__,'exec'),module.__dict__)
            sys.modules[name]=module;modules[name]=module
        yield modules['epoch7_prepare_data'],modules['epoch7_topology_projection']
    finally:
        for name in modules:sys.modules.pop(name,None)


class Gatherer(object):
    """Concrete fixed-path bounded reader using the authenticated loader's IO."""
    def __init__(self,entry,end):
        self.entry,self.end=entry,end;self.trees={};self.rows={};self.total=0;self.socket_evidence=None;self.fresh_evidence=None;self.saved_proof=None;self.saved_topology=None;self.saved_parser=None;self.release_evidence=None;self.release_observation=None
    def check(self):need(time.monotonic()<self.end,'DEADLINE')
    def tree(self,parent):
        self.check()
        if parent not in self.trees:
            need(len(self.trees)<16,'TREE_BOUND')
            self.trees[parent]=self.entry.DescriptorTree(parent)
        return self.trees[parent]
    def read(self,path,maximum,private=False,expected=None):
        self.check();need(type(maximum) is int and 0<maximum<=64*1024*1024,'READ_BOUND')
        need(type(path) is str and path.startswith('/') and os.path.normpath(path)==path,
             'READ_ABSOLUTE_PATH')
        # Callers enumerate paths from fixed constants or hash-authenticated
        # manifests. There is no CLI path-list/provider mechanism.
        roots=(CAND,BASE+'/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5',
               '/etc/xuanjun-development','/etc/systemd/system','/run/systemd/system',
               '/usr/lib/systemd/system','/usr/lib/systemd','/lib/systemd','/usr/bin')
        root=next((r for r in roots if path.startswith(r+'/')),os.path.dirname(path))
        tree=self.tree(root);parent,leaf=tree.parent(path[len(root)+1:])
        before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
        fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        primary=None
        try:
            info=os.fstat(fd)
            owners=((0,0),)
            if path=='/etc/xuanjun-development/p2-native-binding.json':
                need(expected is not None and (expected['uid'],expected['gid'],expected['mode'])==(0,0,0o644),
                     'NATIVE_EXPECTED_AUTHORITY')
                owners=((0,0),)
            need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid) in owners and
                 info.st_nlink==1 and not info.st_mode&0o7022 and info.st_size<=maximum and
                 (not private or stat.S_IMODE(info.st_mode)==0o600), 'FILE_AUTHORITY')
            no_attributes(fd)
            need(stamps(info)==stamps(before),'GATHER_OPEN_RACE')
            chunks=[];count=0
            while True:
                self.check();part=os.read(fd,min(65536,maximum+1-count))
                if not part:break
                count+=len(part);need(count<=maximum,'FILE_BOUND');chunks.append(part)
            raw=b''.join(chunks);no_attributes(fd)
            need(stamps(os.fstat(fd))==stamps(info),'GATHER_FD_RACE')
        except BaseException as error:primary=error;raise
        finally:close_fd(fd,primary)
        after=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
        need(stamps(before)==stamps(after),'GATHER_PATH_RACE')
        row=dict(stamps(after),kind='FILE',sha256=sha(raw))
        need(row['size']==len(raw),'GATHER_SIZE')
        if expected is not None:
            need(all(row[k]==expected[k] and type(row[k]) is type(expected[k]) for k in row),
                 'GATHER_OBSERVATION_DRIFT')
        if path in self.rows:need(self.rows[path]==(raw,row,maximum,private),'GATHER_REPEAT_DRIFT')
        else:
            self.total+=len(raw);need(self.total<=MAX_TOTAL and len(self.rows)<MAX_FILES,'GATHER_TOTAL_BOUND')
            self.rows[path]=(raw,row,maximum,private)
        self.check();return raw,row
    def runtime(self,root,expected):
        raw,unused=self.read(root+'/deploy/integration-manifest.json',2*1024*1024)
        need(sha(raw)==expected,'RUNTIME_MANIFEST_PIN')
        value=self.entry.decode(raw);files=value['files'];need(type(files) is dict and len(files)==102,'OLD102_REQUIRED')
        payload={}
        for name,wanted in sorted(files.items()):
            self.entry.relative(name)
            content,unused=self.read(root+'/'+name,2*1024*1024)
            need(sha(content)==wanted,'OLD_RUNTIME_SOURCE_PIN');payload[name]=content
        return raw,payload
    def recheck(self):
        self.check()
        for path,(raw,row,maximum,private) in tuple(sorted(self.rows.items())):
            again,actual=self.read(path,maximum,private,expected=row)
            need(raw==again and row==actual,'GATHER_FINAL_DRIFT')
        for tree in self.trees.values():self.check();tree.recheck()
        if self.socket_evidence is not None:
            need(self.socket_dropins()==self.socket_evidence,'SOCKET_DROPIN_FINAL_DRIFT')
        if self.fresh_evidence is not None:
            self.saved_unit_dropins(self.saved_proof,self.saved_topology)
        if self.release_evidence is not None:
            self.release_parent(self.release_observation)
        self.check()
    def close(self,primary=None):
        failed=False
        for tree in reversed(list(self.trees.values())):
            if not tree.closed:
                for row in reversed(tree.opened):
                    try:os.close(row[0])
                    except BaseException:failed=True
                tree.closed=True
        self.trees={}
        if failed:
            if primary is None:raise CleanupError()
            primary.preparation_cleanup_failed=True

    def accept_owned_publication(self,publication):
        need(isinstance(publication,Publication) and publication.parent_before[:6]==publication.parent_after[:6],
             'OWNED_PARENT_BINDING')
        matched=False
        for tree in self.trees.values():
            for row in tree.opened:
                if row[3]==CAND:
                    need(row[4]==publication.parent_before,'OWNED_PARENT_BEFORE_DRIFT')
                    need(self.entry.stamp(tree._authority(row[0],True))==publication.parent_after,'OWNED_PARENT_AFTER_DRIFT')
                    row[4]=publication.parent_after;matched=True
        need(matched,'OWNED_PARENT_CAPTURE_REQUIRED')

    def release_parent(self,observation):
        """Measure only the existing release parent and its two ancestors.

        This is fresh B authority, never inserted into the saved observation,
        retained prerequisite inventory, or snapshot. No directory is created.
        """
        self.check()
        need(type(observation) is dict and type(observation.get('policy')) is dict and
             type(observation.get('policy_sha256')) is str and SHA.fullmatch(observation['policy_sha256']) and
             sha(packed(observation['policy'])[:-1])==observation['policy_sha256'],'RELEASE_PARENT_BINDING')
        pins=observation['policy'].get('directories')
        need(type(pins) is dict,'RELEASE_PARENT_ANCESTOR_POLICY')
        owners={(0,0)}
        for path in ('/','/opt',RELEASE_PARENT):
            pin=pins.get(path)
            need(type(pin) is dict and set(pin)=={'uid','gid','mode'} and
                 all(type(value) is int for value in pin.values()) and pin['uid']==0 and
                 0<=pin['gid']<2**32 and 0<=pin['mode']<=0o777 and not pin['mode']&0o022,
                 'RELEASE_PARENT_ANCESTOR_POLICY')
            owners.add((0,pin['gid']))
        if RELEASE_PARENT not in self.trees:
            need(len(self.trees)<16,'TREE_BOUND')
            self.trees[RELEASE_PARENT]=self.entry.DescriptorTree(RELEASE_PARENT,owners=tuple(sorted(owners)))
        tree=self.trees[RELEASE_PARENT];expected=('/', '/opt', RELEASE_PARENT)
        need(tuple(row[3] for row in tree.opened)==expected and set(tree.by_path)==set(expected),
             'RELEASE_PARENT_SCOPE')
        rows={}
        for fd,parent,name,path,before in tree.opened:
            self.check();info=tree._authority(fd,True);no_attributes(fd);row=stamps(info)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and
                 not info.st_mode&0o7022,'RELEASE_PARENT_AUTHORITY')
            need(all(type(value) is int and 0<=value<2**63 for value in row.values()) and
                 row['ino']>0 and row['nlink']>0,'RELEASE_PARENT_AUTHORITY')
            if path==RELEASE_PARENT:
                need((row['uid'],row['gid'],row['mode'])==(0,0,0o750),'RELEASE_PARENT_AUTHORITY')
            pin=pins[path]
            need(all(type(pin[key]) is int and pin[key]==row[key] for key in pin),
                 'RELEASE_PARENT_ANCESTOR_POLICY')
            def rights(value):return ''.join(c if value&n else '-' for n,c in ((4,'r'),(2,'w'),(1,'x')))
            # Both ACL xattrs were actually checked absent above. This is the
            # canonical basic access ACL represented by the measured mode.
            rows[path]=dict(row,kind='DIRECTORY',access_acl='user::%s\ngroup::%s\nother::%s\n' %
                (rights((row['mode']>>6)&7),rights((row['mode']>>3)&7),rights(row['mode']&7)),default_acl='')
        tree.recheck();self.check()
        result={'schema':1,'kind':'FRESH_B_RELEASE_PARENT_AUTHORITY','path':RELEASE_PARENT,
            'observation_sha256':sha(packed(observation)[:-1]),'policy_sha256':observation['policy_sha256'],
            'metadata':rows[RELEASE_PARENT],'ancestors':{path:rows[path] for path in ('/','/opt')},
            'recheck':'PRECOMPILE_MATCHED_FINAL_RECHECK_REQUIRED'}
        if self.release_evidence is not None:
            need(result==self.release_evidence,'RELEASE_PARENT_REPEAT_DRIFT')
        self.release_evidence=copy.deepcopy(result);self.release_observation=observation
        return copy.deepcopy(result)

    def socket_dropins(self):
        roots={}
        for prefix in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system'):
            self.check();tree=self.tree(prefix);parent=tree.fd;leaf='xuanjun-ledger.socket.d';path=prefix+'/'+leaf
            parent_before=stamps(os.fstat(parent));no_attributes(parent)
            try:before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:
                try:os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise ValueError('EPOCH7_PREP_SOCKET_ABSENCE_CHANGED')
                row={'present':False,'metadata':None,'parent_metadata':parent_before,'files':{}}
            else:
                need(stat.S_ISDIR(before.st_mode),'SOCKET_DROPIN_DIRECTORY_TYPE')
                fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);primary=None
                try:
                    info=tree._authority(fd,True);no_attributes(fd)
                    need(stamps(before)==stamps(info),'SOCKET_DROPIN_OPEN_RACE')
                    names=sorted(os.listdir(fd));need(len(names)<=16,'SOCKET_DROPIN_COUNT')
                    files={}
                    for name in names:
                        need(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf',name),'SOCKET_DROPIN_NAME')
                        raw,meta=self.read(path+'/'+name,65536)
                        files[path+'/'+name]={'sha256':sha(raw),'metadata':{k:meta[k] for k in stamps(info)},
                                            'data':raw.decode('utf-8')}
                    need(names==sorted(os.listdir(fd)) and stamps(os.fstat(fd))==stamps(info) and
                         stamps(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==stamps(info),'SOCKET_DROPIN_RACE')
                    row={'present':True,'metadata':stamps(info),'parent_metadata':parent_before,'files':files}
                except BaseException as error:primary=error;raise
                finally:close_fd(fd,primary)
            no_attributes(parent);need(stamps(os.fstat(parent))==parent_before,'SOCKET_PARENT_RACE');tree.recheck()
            roots[path]=row
        result={'schema':1,'unit':'xuanjun-ledger.socket','roots':roots,'reread':'EXACT_PRE_POST'}
        if self.socket_evidence is not None:need(result==self.socket_evidence,'SOCKET_DROPIN_REPEAT_DRIFT')
        self.socket_evidence=result;return copy.deepcopy(result)

    def saved_unit_dropins(self,saved,topology):
        """Compare saved file/presence evidence with independent fresh authority.

        Saved directories have no original identity stamps. Fresh stamps are
        captured here, never fabricated into the accepted saved proof/hash.
        """
        topology.validate_saved_unit_dropins(saved)
        if self.saved_parser is None:
            import unit_metadata
            self.saved_parser=unit_metadata.service_fields
        wanted=saved['dropins_section']['evidence']['units'];units={}
        for unit in sorted(topology.DROPIN_UNITS):
            units[unit]={}
            for prefix in topology.DROPIN_ROOTS:
                self.check();tree=self.tree(prefix);parent=tree.fd;leaf=unit+'.d';path=prefix+'/'+leaf
                expected=wanted[unit][path];parent_before=stamps(os.fstat(parent));no_attributes(parent)
                try:before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:
                    need(expected['present'] is False,'FRESH_DROPIN_PRESENCE')
                    try:os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                    except FileNotFoundError:pass
                    else:raise ValueError('EPOCH7_PREP_FRESH_DROPIN_RACE')
                    row={'present':False,'metadata':None,'parent_metadata':parent_before,'files':{}}
                else:
                    need(expected['present'] is True,'FRESH_DROPIN_PRESENCE')
                    need(stat.S_ISDIR(before.st_mode),'FRESH_DROPIN_DIRECTORY_TYPE')
                    fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);primary=None
                    try:
                        info=tree._authority(fd,True);no_attributes(fd)
                        need(stamps(before)==stamps(info),'FRESH_DROPIN_RACE')
                        names=sorted(os.listdir(fd));need(len(names)<=16,'FRESH_DROPIN_FILE_BOUND')
                        need(set(path+'/'+name for name in names)==set(expected['files']),'FRESH_DROPIN_FILE_SET')
                        files={}
                        for name in names:
                            need(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf',name),'FRESH_DROPIN_FILENAME')
                            target=path+'/'+name;pin=expected['files'][target]
                            raw,meta=self.read(target,65536,expected=pin['metadata'])
                            fields=self.saved_parser(raw)
                            need(sha(raw)==pin['sha256'] and topology.same(fields,pin['public_service_fields']),
                                 'FRESH_DROPIN_FIELDS')
                            files[target]={'sha256':sha(raw),'metadata':meta,'public_service_fields':fields}
                        need(names==sorted(os.listdir(fd)) and stamps(os.fstat(fd))==stamps(info) and
                             stamps(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==stamps(info),'FRESH_DROPIN_RACE')
                        row={'present':True,'metadata':stamps(info),'parent_metadata':parent_before,'files':files}
                    except BaseException as error:primary=error;raise
                    finally:close_fd(fd,primary)
                no_attributes(parent)
                need(stamps(os.fstat(parent))==parent_before,'FRESH_DROPIN_PARENT_RACE');tree.recheck()
                units[unit][path]=row
        result={'schema':1,'kind':'FRESH_R7_UNIT_DROPIN_AUTHORITY',
            'saved_unit_dropins_sha256':topology.digest(topology.canonical(saved)),
            'units':units,'reread':'EXACT_PRE_POST_AND_FINAL'}
        if self.fresh_evidence is not None:
            need(result==self.fresh_evidence and saved==self.saved_proof,'FRESH_DROPIN_REPEAT_DRIFT')
        self.fresh_evidence=copy.deepcopy(result);self.saved_proof=copy.deepcopy(saved);self.saved_topology=topology
        return copy.deepcopy(result)


def no_attributes(fd):
    for name in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,name)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'XATTR_UNKNOWN')
        else:raise ValueError('EPOCH7_PREP_UNREVIEWED_XATTR')


def close_fd(fd,primary=None):
    try:os.close(fd)
    except BaseException:
        if primary is None:raise CleanupError()
        primary.preparation_cleanup_failed=True


def deliver_status(value):
    """One bounded unbuffered status attempt; never retry a partial delivery."""
    try:
        with budget(STATUS_SECONDS) as end:
            raw=packed(value);need(len(raw)<=131072,'PUBLIC_RESULT_BOUND')
            offset=0
            while offset<len(raw):
                need(time.monotonic()<end,'STATUS_DEADLINE')
                count=os.write(1,raw[offset:offset+16384])
                need(type(count) is int and 0<count<=min(16384,len(raw)-offset),'STATUS_WRITE')
                offset+=count
            need(time.monotonic()<end,'STATUS_DEADLINE')
    except BaseException as error:
        failure=StatusDeliveryError()
        failure.preparation_cleanup_failed=bool(getattr(error,'preparation_cleanup_failed',False)) or isinstance(error,CleanupError)
        raise failure from None


def collect_inputs(gather,kit,data,observation_path,observation_sha):
    need(os.path.dirname(observation_path)==CAND and re.fullmatch(
        r'epoch7-observation-[0-9a-f]{16}\.private\.json',os.path.basename(observation_path))
        and type(observation_sha) is str and SHA.fullmatch(observation_sha),'OBSERVATION_INPUT')
    raw,unused=gather.read(observation_path,64*1024*1024,private=True)
    need(sha(raw)==observation_sha,'OBSERVATION_FILE_PIN')
    observation=gather.entry.decode(raw)
    factory=importlib.import_module('epoch7_host_factory')
    data.validate_observation(observation,factory)
    kit._authenticate_probe_receipt(observation)
    receipt=observation['finite_probe']['result']['created_receipt']
    receipt_raw,receipt_metadata=gather.read(receipt['path'],128*1024,private=True)
    receipt_metadata={k:receipt_metadata[k] for k in data.STAT_FIELDS}
    original,unused=gather.read(CAND+'/protected-core-install-plan.json',2*1024*1024,private=True)
    need(sha(original)==data.ORIGINAL_PLAN,'ORIGINAL_PLAN_PIN')
    v4_kit=CAND+'/epoch5-recovery-candidate-v4'
    oldkit,unused=gather.read(v4_kit+'/recovery-kit-manifest.json',2*1024*1024)
    helpers={name:gather.read(v4_kit+'/helpers/'+name+'.py',65536)[0] for name in data.V4_ORDER}
    oldmanifest,oldpayloads=gather.runtime(data.ORIGINAL_ROOT,data.ORIGINAL_MANIFEST)
    v4manifest,v4payloads=gather.runtime(data.V4_ROOT,data.V4_MANIFEST)
    v4plan=data.reproduce_v4(original,oldmanifest,oldpayloads,v4manifest,v4payloads,oldkit,helpers)
    cached=kit.cache;prefix='xuanjun-p2-package/'
    manifest_raw=cached[prefix+data.MANIFEST_PATH];manifest=gather.entry.decode(manifest_raw)
    payloads={name:cached[prefix+name] for name in manifest['files']}
    compiled=data.compile_bindings(v4plan,v4manifest,v4payloads,manifest_raw,payloads,observation,factory)
    rows={}
    for name,path in data.RAW_PATHS.items():
        expected=observation['evidence']['retained']['files'][path]
        raw,meta=gather.read(path,2*1024*1024,private=expected['mode']==0o600,expected=expected)
        rows[name]={'raw':raw,'metadata':meta}
    buffers=data.retained_buffers(observation,rows)
    manager_evidence=observation['evidence']['writers']['manager']
    manager=manager_evidence['binary_path']
    need(manager in ('/usr/lib/systemd/systemd','/lib/systemd/systemd'),'MANAGER_PATH')
    measured=observation['evidence']['retained']['files'];manager_file=measured[manager]
    need(manager_evidence['binary_sha256']==manager_file['sha256'] and
         type(manager_evidence['binary_identity']) is list and
         all(type(value) is int for value in manager_evidence['binary_identity']) and
         manager_evidence['binary_identity']==[manager_file['dev'],manager_file['ino']],
         'MANAGER_OBSERVATION_BINDING')
    # Server policy compiler requires actual source bytes for these two public
    # executables. Hash-only observations cannot substitute for those inputs.
    tools={}
    for label,path in (('systemd',manager),('systemctl','/usr/bin/systemctl')):
        pin=observation['policy']['executables'][label];expected=measured[path]
        need(pin['path']==path and pin['sha256']==expected['sha256'],'TOOL_OBSERVATION_BINDING')
        raw,unused=gather.read(path,16*1024*1024,expected=expected)
        tools[path]=raw
    gather.recheck()
    return {'observation':observation,'compiled':compiled,'buffers':buffers,'manifest_raw':manifest_raw,
        'source_payloads':payloads,'tool_sources':tools,'receipt_raw':receipt_raw,
        'receipt_metadata':receipt_metadata,'v4_plan_sha256':sha(v4plan)}


def server_policy(observation,compiled,manifest_raw,payloads,tool_sources,topology_raw,review,data,socket_dropins):
    import epoch7_additive_server as server
    topology=data.parse(topology_raw,131072);release='/opt/xuanjun-control-releases/integration-'+sha(manifest_raw)[:16]+'/stage1'
    units={}
    for unit in server.UNIT_PROPERTIES:
        units[unit]={'Id':unit,'LoadState':'loaded','NeedDaemonReload':'no',
            'FragmentPath':'/etc/systemd/system/'+unit,'DropInPaths':''}
    # These are proposed post-install properties of the exact rendered units,
    # not fabricated live measurements. The additive compiler binds their bytes.
    units[server.SOCKET_UNIT].update(Listen=server.SOCKET_PATH+' (Stream)',Accept='no',Triggers=server.SERVICE_UNIT,
        SocketUser='xuanjun-dispatcher',SocketGroup='xuanjun-ledger-client',SocketMode='0660',DirectoryMode='0711',RemoveOnStop='yes')
    units[server.SERVICE_UNIT].update(User='xuanjun-dispatcher',Group='xuanjun-control-db',
        ExecStart=server.expected_exec_start(release),WorkingDirectory=release,TriggeredBy=server.SOCKET_UNIT)
    # Unexpected measured drop-ins cannot be silently excluded from policy.
    from epoch7_topology_projection import validate_saved_unit_dropins
    validate_saved_unit_dropins(socket_dropins)
    inventories=observation['unit_metadata']['sections']['dropins']['evidence']['units']
    service_inventory=inventories[server.SERVICE_UNIT]
    expected_roots={p+'/'+server.SERVICE_UNIT+'.d' for p in
        ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
    need(set(service_inventory)==expected_roots,'LEDGER_SERVICE_DROPIN_ROOTS')
    for row in service_inventory.values():
        need(type(row.get('present')) is bool and row.get('files')=={},'LEDGER_SERVICE_DROPINS_REQUIRE_REVIEW')
    for unit in units:
        state=observation['evidence']['writers']['units'][unit]['state']
        need(state['DropInPaths']=='' and state['NeedDaemonReload']=='no','LEDGER_DROPINS_REQUIRE_REVIEW')
    sources=dict(tool_sources)
    manager=observation['evidence']['writers']['manager']
    need(set(sources)=={manager['binary_path'],'/usr/bin/systemctl'} and
         sha(sources[manager['binary_path']])==manager['binary_sha256'] and
         sha(sources['/usr/bin/systemctl'])==observation['policy']['executables']['systemctl']['sha256'],
         'SERVER_TOOL_MEASURED_BINDING')
    sources[release+'/ledger_service.py']=payloads['stage1/ledger_service.py']
    for unit in units:sources['/etc/systemd/system/'+unit]=compiled['rendered_targets']['/etc/systemd/system/'+unit]
    creator=dict(topology['creator'],topology_evidence_sha256=sha(topology_raw))
    policy={'schema':2,'trust_model':'ROOT_MANAGER_DELIVERY_V1','exclusive_delivery_reviewed':True,
        'activation_binding':{k:compiled['activation_proposal'][k] for k in server.BINDING_KEYS},
        'creator':creator,'endpoint':dict(topology['endpoint_identity'],path=server.SOCKET_PATH),
        'files':{p:sha(raw) for p,raw in sources.items()},'units':units}
    raw=packed(policy)
    delta=server.compile_addition(raw,sha(raw),manifest_raw,sha(manifest_raw),sources,topology_raw,review,
                                  data.additive_absence(observation,server.PATH))
    return raw,delta


def compile_private_bundle(kit,collected,topology_raw,review,timer,data):
    """Pure after authenticated collection/review. No writes or host assembly."""
    need(type(timer) is bool,'EXPLICIT_TIMER_DECISION')
    need(timer is True,'RETAINED_TIMER_SCHEDULE_MUST_BE_REVIEWED')
    factory=importlib.import_module('epoch7_host_factory')
    owner=importlib.import_module('epoch7_additive_identity')
    server=importlib.import_module('epoch7_additive_server')
    approval=importlib.import_module('epoch7_complete_approval')
    gate=importlib.import_module('epoch7_injected_recovery')
    observation=collected['observation'];compiled=collected['compiled'];manifest=collected['manifest_raw']
    owner_raw,owner_delta=data.owner_policy(observation,compiled,manifest)
    server_raw,server_delta=server_policy(observation,compiled,manifest,collected['source_payloads'],
        collected['tool_sources'],topology_raw,review,data,collected['socket_dropins'])
    additions=sorted((owner_delta,server_delta),key=lambda row:row['path'])
    need(type(collected.get('fresh_unit_authority')) is dict and
         collected['fresh_unit_authority']['saved_unit_dropins_sha256']==sha(data.canonical(collected['socket_dropins'])),
         'FRESH_DROPIN_SAVED_BINDING')
    private=dict(collected['buffers'],observation=observation,compiled=compiled,
        additive_deltas=additions,identity_payloads={owner.PATH:owner_raw,server.PATH:server_raw},
        activate_retained_renewal_timer=timer,
        fresh_release_parent=copy.deepcopy(collected['fresh_release_parent']))
    # Hydration uses only the loader's authenticated current runtime cache.
    wire_private=copy.deepcopy(private)
    for key in data.RAW_PATHS:wire_private[key]=wire_private[key].decode('utf-8')
    for key in ('rendered_targets','old_rendered_targets'):
        wire_private['compiled'][key]={p:raw.decode('utf-8') for p,raw in wire_private['compiled'][key].items()}
    wire_private['compiled']['tls_config_bytes']=wire_private['compiled']['tls_config_bytes'].decode('utf-8')
    wire_private['identity_payloads']={p:raw.decode('utf-8') for p,raw in wire_private['identity_payloads'].items()}
    seed=kit._hydrate_seed(wire_private,factory)
    prepared=factory.prepare_host_inputs(seed)
    need(prepared['state']=='COMPILED_NOT_ADMITTED' and prepared['unresolved']==[] and
         prepared['install_admission'] is False,'PREPARATION_UNRESOLVED')
    inputs=prepared['inputs'];plan=factory.compile_host_contract(inputs);plan_raw=packed(plan)
    need(len(plan_raw)<=2*1024*1024,'PLAN_BOUND')
    delta=factory.d.build_delta(inputs['snapshot'],factory.d.digest(inputs['snapshot']),inputs['candidate'])
    authorization=gate.required_authorization(delta,kit.digest,factory.d.digest(inputs['access_rows']),additions)
    body=approval.expected_complete_from_inputs(sha(plan_raw),delta,authorization)
    seed_raw=data.seed_wire(seed)
    return {'plan_raw':plan_raw,'seed_raw':seed_raw,'unsigned_approval':body,
        'summary':{'schema':1,'state':'PREPARED_NOT_ADMITTED','kit_manifest_sha256':kit.digest,
            'snapshot_sha256':observation['snapshot_sha256'],'plan_sha256':sha(plan_raw),
            'seed_sha256':sha(seed_raw),'topology_sha256':sha(topology_raw),
            'topology_review':copy.deepcopy(review),'target_count':26,'resource_checkpoints':17,
            'retained_timer_scheduling_review_required':True,'install_admission':'NOT_GRANTED',
            'production_resume':'NOT_EXECUTED','production_acceptance':'PENDING',
            'fresh_unit_authority_sha256':sha(data.canonical(collected['fresh_unit_authority'])),
            'fresh_release_parent_sha256':sha(data.canonical(collected['fresh_release_parent'])),
            'saved_evidence_kit_manifest_sha256':KIT_SHA},
        'fresh_unit_authority':copy.deepcopy(collected['fresh_unit_authority']),
        'fresh_release_parent':copy.deepcopy(collected['fresh_release_parent'])}


class Publication(list):
    """Internal own-write proof; only list elements are emitted as JSON."""
    pass


def parent_inventory(fd):
    names=os.listdir(fd)
    need(len(names)<=1024 and all(type(name) is str and 0<len(name)<=255 and
         '/' not in name and '\x00' not in name for name in names),'OUTPUT_PARENT_INVENTORY_BOUND')
    need(len(names)==len(set(names)),'OUTPUT_PARENT_INVENTORY_DUPLICATE')
    return tuple(sorted(names))


def verify_publication(entry,publication,end):
    need(isinstance(publication,Publication) and len(publication)==3,'COMPLETE_PUBLICATION_REQUIRED')
    reader=Gatherer(entry,end);primary=None
    try:
        tree=reader.tree(CAND)
        need(entry.stamp(tree._authority(tree.fd,True))==publication.parent_after,'PUBLICATION_PARENT_CHANGED')
        need(parent_inventory(tree.fd)==publication.parent_names_after,'PUBLICATION_PARENT_INVENTORY_CHANGED')
        for row in publication:
            path=row['path'];raw,metadata=reader.read(path,publication.bounds[path],private=True,expected=publication.metadata[path])
            need(raw==publication.raws[path] and sha(raw)==row['sha256'],'PUBLICATION_BYTES_CHANGED')
        reader.recheck()
    except BaseException as error:primary=error;raise
    finally:reader.close(primary)


def publish_bundle(entry,bundle,proposal,source_manifest,end):
    """Create three new protected outputs; never overwrite or remove any file.

    The caller has completed collection, current review authentication and all
    pure compilation. Partial creation remains protected and is reported HOLD.
    The final receipt is written last and is not an installation authority.
    """
    packet={'schema':1,'state':'PREPARED_NOT_ADMITTED','summary':bundle['summary'],
        'preparation_sources':source_manifest,
        'preparation_source_manifest_sha256':sha(packed(source_manifest)[:-1]),
        'saved_projection_sources':copy.deepcopy(SAVED_PROJECTION_SOURCES),
        'saved_projection_source_manifest_sha256':SAVED_PROJECTION_MANIFEST_SHA,
        'fresh_unit_authority':bundle.get('fresh_unit_authority'),
        'fresh_release_parent':bundle['fresh_release_parent'],
        'saved_evidence_kit_manifest_sha256':KIT_SHA,'compiler_kit_manifest_sha256':COMPILER_KIT_SHA,
        'topology_review_body':proposal['expected_review_body'],
        'final_review_body':bundle['unsigned_approval'],
        'timer_scope':{'enable_after_post_install_checks':True,'minimum_first_expiry_margin_seconds':180,
            'explicit_certbot_invocations':0,'retained_certificate_ready_required':True},
        'final_review_id':None,'final_review_body_sha256':None,'production_acceptance':'PENDING'}
    rows=[('epoch7-approved-plan-',bundle['plan_raw'],2*1024*1024),
          ('epoch7-resume-inputs-',bundle['seed_raw'],64*1024*1024),
          ('epoch7-review-packet-',packed(packet),2*1024*1024)]
    need(all(type(raw) is bytes and 0<len(raw)<=maximum for prefix,raw,maximum in rows),'ALL_OUTPUT_BOUNDS')
    names=[prefix+sha(raw)[:16]+'.private.json' for prefix,raw,maximum in rows]
    tree=entry.DescriptorTree(CAND);primary=None;outputs=Publication();created=[]
    outputs.metadata={};outputs.raws={};outputs.bounds={}
    try:
        outputs.parent_before=entry.stamp(tree._authority(tree.fd,True))
        outputs.parent_names_before=parent_inventory(tree.fd)
        need(entry.stamp(tree._authority(tree.fd,True))==outputs.parent_before,'OUTPUT_PARENT_INVENTORY_RACE')
        for name in names:
            try:os.stat(name,dir_fd=tree.fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise ValueError('EPOCH7_PREP_OUTPUT_EXISTS')
        tree.recheck()
        for name,(prefix,raw,maximum) in zip(names,rows):
            need(type(raw) is bytes and 0<len(raw)<=maximum and time.monotonic()<end,'OUTPUT_BOUND')
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=tree.fd)
            created.append(CAND+'/'+name)
            file_primary=None
            try:
                info=os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),
                     'OUTPUT_AUTHORITY');no_attributes(fd)
                offset=0
                while offset<len(raw):
                    need(time.monotonic()<end,'OUTPUT_DEADLINE')
                    count=os.write(fd,raw[offset:offset+65536]);need(count>0,'OUTPUT_SHORT_WRITE');offset+=count
                os.fsync(fd);need(time.monotonic()<end,'OUTPUT_DEADLINE')
                after=os.fstat(fd);linked=os.stat(name,dir_fd=tree.fd,follow_symlinks=False)
                need(after.st_ino==info.st_ino and after.st_dev==info.st_dev and after.st_size==len(raw) and
                     stamps(after)==stamps(linked),'OUTPUT_BINDING')
            except BaseException as error:file_primary=error;raise
            finally:close_fd(fd,file_primary)
            readback=tree.read(name,maximum,private=True)
            need(readback==raw and time.monotonic()<end,'OUTPUT_READBACK')
            outputs.append({'path':CAND+'/'+name,'sha256':sha(raw),'bytes':len(raw)})
            outputs.metadata[CAND+'/'+name]=dict(stamps(after),kind='FILE',sha256=sha(raw))
            outputs.raws[CAND+'/'+name]=raw;outputs.bounds[CAND+'/'+name]=maximum
        os.fsync(tree.fd);need(time.monotonic()<end,'OUTPUT_DEADLINE')
        # CAND's own size/times changed only through exclusive creations. Keep
        # its identity/mode/owner and every ancestor/path binding exact.
        for fd,parent,name,path,before in tree.opened:
            now=entry.stamp(tree._authority(fd,True))
            need((now[:6]==before[:6] if path==CAND else now==before),'OUTPUT_PARENT_CHANGED')
            if parent is not None:need(entry.stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==now,'OUTPUT_PARENT_LINK')
        outputs.parent_after=entry.stamp(tree._authority(tree.fd,True))
        outputs.parent_names_after=tuple(sorted(outputs.parent_names_before+tuple(names)))
        need(parent_inventory(tree.fd)==outputs.parent_names_after and
             entry.stamp(tree._authority(tree.fd,True))==outputs.parent_after,'OUTPUT_UNOWNED_DIRECTORY_CHANGE')
        verify_publication(entry,outputs,end)
        return outputs
    except BaseException as error:
        primary=error;error.preparation_outputs=copy.deepcopy(list(outputs));error.preparation_created_paths=list(created);raise
    finally:
        failed=False
        for row in reversed(tree.opened):
            try:os.close(row[0])
            except BaseException:failed=True
        tree.closed=True
        if failed:
            if primary is None:
                error=CleanupError();error.preparation_outputs=copy.deepcopy(list(outputs));error.preparation_created_paths=list(created);raise error
            primary.preparation_cleanup_failed=True


def run_preparation(args,end):
    require_binding();require_compiler_binding()
    need(args.observation==OBSERVATION_PATH and args.observation_sha256==OBSERVATION_SHA,'FIXED_R7_OBSERVATION')
    need(args.operation=='prepare' and type(args.topology_review_id) is int and args.topology_review_id>0 and
         args.retained_renewal_timer=='enable-after-reviewed-checks','GENUINE_REVIEW_AND_EXPLICIT_TIMER_REQUIRED')
    need(os.geteuid()==0 and __import__('socket').gethostname()==HOST,'EXACT_ROOT_HOST')
    phase('BOOTSTRAP');entry=bootstrap_entry();phase('VERIFY_KIT');kit=entry.verify_kit(KIT_ROOT,KIT_SHA)
    phase('VERIFY_COMPILER_KIT');compiler_entry=bootstrap_entry(compiler=True)
    compiler_kit=compiler_entry.verify_kit(COMPILER_KIT_ROOT,COMPILER_KIT_SHA)
    gather=Gatherer(entry,end);primary=None;outputs=None
    try:
        phase('LOAD_PREPARATION_SOURCES')
        cache,source_manifest=preparation_sources(gather)
        with contextlib.ExitStack() as preparation_scope:
          with kit.imports():
            data,topology=preparation_scope.enter_context(preparation_modules(cache))
            phase('COLLECT_INPUTS')
            collected=collect_inputs(gather,kit,data,args.observation,args.observation_sha256)
            source_files={name:kit.cache[kit.manifest['modules'][name[:-3]]] for name in
                ('probe_driver.py','probe_helpers.py','node_sqlite_probe.py','unit_metadata.py','snapshot_io.py')}
            saved=topology.project_saved_unit_dropins(collected['observation'])
            phase('FRESH_UNIT_AUTHORITY')
            collected['fresh_unit_authority']=gather.saved_unit_dropins(saved,topology)
            collected['socket_dropins']=saved
            phase('FRESH_RELEASE_PARENT')
            collected['fresh_release_parent']=gather.release_parent(collected['observation'])
            source_files['deploy/integration-manifest.json']=collected['manifest_raw']
            phase('PROJECT_TOPOLOGY');proposal=topology.project_topology(collected['observation'],collected['receipt_raw'],
                collected['receipt_metadata'],kit.digest,source_files,saved,SAVED_PROJECTION_MANIFEST_SHA)
            need(sha(topology.canonical(proposal['expected_review_body']))==EXPECTED_REVIEW_BODY_SHA,'ACCEPTED_REVIEW_BODY_PIN')
            need(args.topology_review_id is not None and args.retained_renewal_timer=='enable-after-reviewed-checks',
                 'GENUINE_REVIEW_AND_EXPLICIT_TIMER_REQUIRED')
            phase('FETCH_TOPOLOGY_REVIEW');review=topology.fetch_topology_review(args.topology_review_id,proposal)
            gather.check()
            kit._authenticate_probe_receipt(collected['observation']);gather.recheck()
          with compiler_kit.imports():
            prefix='xuanjun-p2-package/'
            need(compiler_kit.cache[prefix+data.MANIFEST_PATH]==collected['manifest_raw'] and
                 all(compiler_kit.cache[prefix+name]==raw for name,raw in collected['source_payloads'].items()),
                 'COMPILER_RUNTIME_CHANGED')
            phase('COMPILE_PRIVATE_BUNDLE')
            bundle=compile_private_bundle(compiler_kit,collected,proposal['topology_raw'],review,True,data)
            gather.recheck()
        # Reauthenticate every frozen kit byte after compilation and again
        # after publication. Only this attempt's exact CAND stamp transition
        # may be incorporated into the retained read-only ancestry capture.
        phase('VERIFY_BEFORE_PUBLICATION');again=entry.verify_kit(KIT_ROOT,KIT_SHA)
        need(again.raw_manifest==kit.raw_manifest and again.cache==kit.cache,'KIT_FINAL_CHANGED')
        compiler_again=compiler_entry.verify_kit(COMPILER_KIT_ROOT,COMPILER_KIT_SHA)
        need(compiler_again.raw_manifest==compiler_kit.raw_manifest and compiler_again.cache==compiler_kit.cache,
             'COMPILER_KIT_FINAL_CHANGED')
        gather.recheck();gather.check()
        phase('PUBLISH_OUTPUTS');outputs=publish_bundle(entry,bundle,proposal,source_manifest,end)
        phase('VERIFY_AFTER_PUBLICATION')
        gather.accept_owned_publication(outputs);gather.recheck()
        again=entry.verify_kit(KIT_ROOT,KIT_SHA)
        need(again.raw_manifest==kit.raw_manifest and again.cache==kit.cache,'KIT_POST_PUBLICATION_CHANGED')
        compiler_again=compiler_entry.verify_kit(COMPILER_KIT_ROOT,COMPILER_KIT_SHA)
        need(compiler_again.raw_manifest==compiler_kit.raw_manifest and compiler_again.cache==compiler_kit.cache,
             'COMPILER_KIT_POST_PUBLICATION_CHANGED')
        gather.recheck();verify_publication(entry,outputs,end);gather.check()
        return dict(bundle['summary'],outputs=list(outputs),final_review='REQUIRED',
                    fresh_release_parent_final_recheck='MATCHED_AFTER_PUBLICATION',
                    expected_complete_review_body=copy.deepcopy(bundle['unsigned_approval']))
    except BaseException as error:
        primary=error
        if outputs is not None:
            error.preparation_outputs=copy.deepcopy(list(outputs));error.preparation_created_paths=[row['path'] for row in outputs]
        raise
    finally:
        try:gather.close(primary)
        except BaseException as error:
            if outputs is not None:
                error.preparation_outputs=copy.deepcopy(list(outputs));error.preparation_created_paths=[row['path'] for row in outputs]
            raise


def main(argv=None):
    phase('INPUT_VALIDATION')
    class Parser(argparse.ArgumentParser):
        def error(self,unused):raise ValueError('EPOCH7_PREP_ARGUMENTS')
    parser=Parser(description=__doc__,add_help=False)
    parser.add_argument('--operation',choices=('input-contract','prepare'),required=True)
    parser.add_argument('--observation');parser.add_argument('--observation-sha256')
    parser.add_argument('--topology-review-id',type=int)
    parser.add_argument('--retained-renewal-timer',choices=('enable-after-reviewed-checks',))
    args=parser.parse_args(argv)
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ISOLATED_NO_BYTECODE')
    if args.operation=='input-contract':
        phase('DELIVER_STATUS')
        deliver_status({'schema':1,'operation':args.operation,'state':'PREPARATION_REQUIRES_REVIEW',
            'kit_manifest_sha256':KIT_SHA,'compiler_kit_manifest_sha256':COMPILER_KIT_SHA,
            'compiler_artifact_bound':COMPILER_KIT_SHA is not None,'fixed_raw_buffer_count':6,'historical_package_file_counts':[102,102],
            'candidate_package_file_count':107,'independent_saved_units':11,'independent_fresh_dropin_roots':33,
            'required':['EXACT_COMPLETE_OBSERVATION_AND_ROOT_RECEIPT','GENUINE_TOPOLOGY_REVIEW','EXPLICIT_TIMER_SCOPE','FINAL_COMPLETE_APPROVAL'],
            'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'});return 0
    need(type(args.observation) is str and type(args.observation_sha256) is str,'OBSERVATION_INPUT_REQUIRED')
    need(type(args.topology_review_id) is int and args.topology_review_id>0 and
              args.retained_renewal_timer=='enable-after-reviewed-checks','GENUINE_REVIEW_AND_EXPLICIT_TIMER_REQUIRED')
    result=None
    try:
        with budget() as end:
            result=run_preparation(args,end);phase('FINALIZE_BUDGET')
    except BaseException as error:
        if type(result) is dict and type(result.get('outputs')) is list:
            error.preparation_outputs=copy.deepcopy(result['outputs'])
            error.preparation_created_paths=[row['path'] for row in result['outputs']]
        raise
    phase('DELIVER_STATUS');deliver_status(result);return 0


def entrypoint(argv=None):
    try:return main(argv)
    except BaseException as error:
        if isinstance(error,SystemExit):raise
        if isinstance(error,StatusDeliveryError):return 2
        label=(error.args[0] if type(error) is ValueError and len(error.args)==1 and
               type(error.args[0]) is str and error.args[0] in SAFE_FAILURE_LABELS else None)
        status={'state':'HOLD','failure_code':type(error).__name__,'failure_label':label,'phase':CURRENT_PHASE,
            'cleanup_unknown':isinstance(error,CleanupError) or bool(getattr(error,'preparation_cleanup_failed',False)),
            'completed_outputs':getattr(error,'preparation_outputs',[]),
            'created_output_paths':getattr(error,'preparation_created_paths',[]),
            'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
        try:deliver_status(status)
        except StatusDeliveryError:pass
        return 2


if __name__=='__main__':sys.exit(entrypoint())
