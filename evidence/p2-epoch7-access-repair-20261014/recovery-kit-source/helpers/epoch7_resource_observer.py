"""Finite reviewed read-only resource projections for phase checkpoints.

Specs contain no future inode or timestamp guesses. Full immediate CAS belongs
in each concrete effect; fixed preserved identities may additionally pin dev/ino.
Every spec is inside the independently approved complete plan. No default views.
"""
import copy
import hashlib
import json
import os
import pwd
import grp
import stat
import time

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_protected_fs as fs
import epoch7_python_identity as python_identity
from epoch7_live_controls import PHASES, SECTIONS
from epoch7_exact_access import get_attr, decode_acl, ACCESS, DEFAULT
from epoch7_host_phases import need, sha

MAX_BYTES=536870912
DIRECTORY_FIELDS={'uid','gid','mode','access_acl','default_acl'}
FILE_FIELDS={'path','kind','uid','gid','mode','sha256','access_acl'}


def same_node_reference(actual,expected,authority):
    """Allow only the config parent's timestamps after this attempt's write.

    The concrete sampler still double-checks every stamp. Historical link/ELF,
    all other ancestors and this parent's inode/authority/nlink remain exact.
    """
    from unit_metadata import validate_node_reference
    final=expected['final'];validate_node_reference(expected,final['path'],final['sha256'])
    validate_node_reference(actual,final['path'],final['sha256'])
    if actual==expected:return True
    projected=copy.deepcopy(actual);parent=os.path.dirname(snap.PROFILE)
    for key in ('size','mtime_ns','ctime_ns'):
        projected['ancestors'][parent][key]=expected['ancestors'][parent][key]
    need(projected==expected,'RESOURCE_NODE_REFERENCE_IMMUTABLE_DRIFT')
    authority.receipt();need(authority.io is not None,'RESOURCE_NODE_OWNED_CONFIG_RECEIPT_REQUIRED')
    from epoch7_recovery_sequence import OUTER_NAME
    outer=authority.validate_outer(authority.io.read_journal(OUTER_NAME)['data'])['state']
    index=PHASES.index('apply_fresh_sandbox');permitted=False
    for phase_index,phase in enumerate(PHASES):
        if phase_index<index:continue
        for suffix,completed in (('_INTENT',list(PHASES[:phase_index])),
                                 ('_COMPLETE',list(PHASES[:phase_index+1]))):
            if outer.get('stage')==phase+suffix and outer.get('completed')==completed:
                permitted=True
    need(outer.get('admission')=='ADMITTED' and permitted,'RESOURCE_NODE_OWNED_CONFIG_PHASE_REQUIRED')
    name=fs.TRANSACTION+'/epoch7-sandbox-profile.json'
    parent_fd,leaf=authority.io._parent(name)
    try:metadata,raw=authority.io._read_at(parent_fd,leaf,maximum=65536)
    finally:os.close(parent_fd)
    need((metadata['uid'],metadata['gid'],metadata['mode'],metadata['nlink'])==(0,0,0o600,1),
         'RESOURCE_NODE_PRIVATE_SANDBOX_RECEIPT')
    row=snap.decode(raw)
    need(type(row) is dict and set(row)=={'schema','context_sha256','original_sha256','candidate_sha256',
         'current_sha256','state'} and type(row['schema']) is int and row['schema']==1 and
         row['context_sha256']==authority.context['context_sha256'] and row['state'] in ('APPLIED','CLI_CAPTURED'),
         'RESOURCE_NODE_OWNED_CONFIG_RECEIPT_REQUIRED')
    for key in ('original_sha256','candidate_sha256','current_sha256'):d.hash_value(row[key])
    need(row['state']!='APPLIED' or row['current_sha256']==row['candidate_sha256'],
         'RESOURCE_NODE_OWNED_CONFIG_HASH_REQUIRED')
    need(row['state']!='CLI_CAPTURED' or 'apply_fresh_sandbox' in outer['completed'],
         'RESOURCE_NODE_CLI_AFTER_SANDBOX_REQUIRED')
    authority.receipt();return True


class ResourceReader(object):
    """Actual fd-relative reader accepting only explicitly reviewed ancestor ACLs."""
    def __init__(self,directories,authority,root='/'):
        need(type(directories) is dict and 1<=len(directories)<=8192 and '/' in directories,
             'RESOURCE_DIRECTORY_POLICY')
        self.directories=copy.deepcopy(directories);self.authority=authority
        need(os.path.isabs(root) and os.path.realpath(root)==root,'RESOURCE_ROOT_CANONICAL')
        if root!='/':
            base=os.path.join(os.path.dirname(os.path.realpath(__file__)),'fixtures')
            need(root.startswith(base+'/'),'RESOURCE_FIXTURE_CONFINEMENT')
        self.root=root;self.root_identity=fs.stamp(os.lstat(root))[:5];self.deadline=None;self.guard_deadline=None
        for path,rows in self.directories.items():
            need(path=='/' or (path.startswith('/') and os.path.normpath(path)==path),'RESOURCE_DIRECTORY_PATH')
            need(type(rows) is list and 1<=len(rows)<=3,'RESOURCE_FINITE_ANCESTOR_STATES')
            for row in rows:
                need(type(row) is dict and set(row) in (DIRECTORY_FIELDS,DIRECTORY_FIELDS|{'dev','ino'}),
                     'RESOURCE_ANCESTOR_FIELDS')
                need(row['default_acl']=='' and not row['mode']&0o022,'RESOURCE_ANCESTOR_AUTHORITY')

    def start(self):self.deadline=min(time.monotonic()+30,self.guard_deadline if self.guard_deadline is not None else float('inf'))
    def check(self):
        self.authority.receipt()
        need(self.deadline is not None and time.monotonic()<self.deadline,'RESOURCE_TOTAL_DEADLINE')

    def _directory(self,fd,path):
        info=os.fstat(fd);need(stat.S_ISDIR(info.st_mode),'RESOURCE_DIRECTORY_REQUIRED')
        row={k:fs.metadata(info)[k] for k in ('uid','gid','mode','dev','ino')}
        row['access_acl']=decode_acl(get_attr(fd,ACCESS),row['mode'])
        need(get_attr(fd,DEFAULT) is None,'RESOURCE_DEFAULT_ACL');row['default_acl']=''
        wanted=self.directories.get(path)
        need(wanted is not None and any(all(row[k]==v for k,v in item.items()) for item in wanted),
             'RESOURCE_ANCESTOR_DRIFT')
        return row

    def _parent(self,path):
        need(type(path) is str and path.startswith('/') and path!='/' and os.path.normpath(path)==path
             and '\0' not in path and len(path)<=4096,'RESOURCE_PATH')
        self.check();fd=os.open(self.root,fs.DIR_FLAGS);held=[fd];links=[]
        try:
            need(fs.stamp(os.fstat(fd))[:5]==self.root_identity,'RESOURCE_ROOT_CHANGED')
            self._directory(fd,'/');at=''
            for part in path.strip('/').split('/')[:-1]:
                self.check();at+='/'+part;before=os.stat(part,dir_fd=fd,follow_symlinks=False)
                child=os.open(part,fs.DIR_FLAGS,dir_fd=fd);held.append(child)
                need(fs.stamp(before)==fs.stamp(os.fstat(child)),'RESOURCE_ANCESTOR_OPEN_RACE')
                self._directory(child,at);links.append((fd,part,child,before));fd=child
            return held,links,fd,path.rsplit('/',1)[1]
        except BaseException:
            for fd in reversed(held):os.close(fd)
            raise

    def _finish(self,held,links):
        try:
            for parent,name,fd,before in links:
                need(fs.stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))[:5]==fs.stamp(before)[:5]
                     and fs.stamp(os.fstat(fd))[:5]==fs.stamp(before)[:5],'RESOURCE_ANCESTOR_REPLACED')
            need(fs.stamp(os.lstat(self.root))[:5]==self.root_identity,'RESOURCE_ROOT_REPLACED')
        finally:
            for fd in reversed(held):os.close(fd)

    def _python_metadata(self,fd,kind):
        """No-follow pair descriptors only; unreadable xattrs are a hard failure."""
        self.check();before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) if kind=='FILE' else stat.S_ISDIR(before.st_mode),
             'RESOURCE_PYTHON_PAIR_KIND')
        row=dict(fs.metadata(before),kind=kind)
        for key,name in (('access_acl',ACCESS),('default_acl',DEFAULT),('capability','security.capability')):
            row[key]=get_attr(fd,name) is not None
        need(fs.stamp(os.fstat(fd))==fs.stamp(before),'RESOURCE_PYTHON_PAIR_METADATA_RACE')
        return row

    def _python_pair_sample(self):
        """Read both fixed names while retaining every file/ancestor descriptor.

        A second independent round is required by python_file. No execution or
        package lookup occurs. Full metadata and xattrs are checked again before
        closing descriptors; the central validator binds both rounds to the plan.
        """
        records=[];sample={'files':{},'ancestors':{}}
        try:
            for path in python_identity.PYTHON_PATHS:
                self.check();held,links,parent,leaf=self._parent(path)
                record={'held':held,'links':links,'parent':parent,'leaf':leaf,'fd':None,'ancestors':[]}
                records.append(record)
                need(len(held)==len(python_identity.ANCESTOR_PATHS),'RESOURCE_PYTHON_PAIR_ANCESTORS')
                for ancestor,fd in zip(python_identity.ANCESTOR_PATHS,held):
                    row=self._python_metadata(fd,'DIRECTORY')
                    need(ancestor not in sample['ancestors'] or sample['ancestors'][ancestor]==row,
                         'RESOURCE_PYTHON_PAIR_ANCESTOR_RACE')
                    sample['ancestors'][ancestor]=row;record['ancestors'].append((fd,row))
                before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                need(stat.S_ISREG(before.st_mode) and before.st_nlink==2 and
                     before.st_size==python_identity.RETAINED_SIZE,'RESOURCE_PYTHON_PAIR_FILE_BOUND')
                fd=os.open(leaf,fs.READ_FLAGS,dir_fd=parent);record['fd']=fd
                need(fs.stamp(os.fstat(fd))==fs.stamp(before),'RESOURCE_PYTHON_PAIR_OPEN_RACE')
                row=self._python_metadata(fd,'FILE');record['metadata']=row;record['before']=before
                chunks=[];count=0
                while True:
                    self.check();raw=os.read(fd,min(65536,python_identity.RETAINED_SIZE+1-count))
                    if not raw:break
                    chunks.append(raw);count+=len(raw)
                    need(count<=python_identity.RETAINED_SIZE,'RESOURCE_PYTHON_PAIR_READ_BOUND')
                need(count==before.st_size,'RESOURCE_PYTHON_PAIR_READ_SIZE');raw=b''.join(chunks)
                sample['files'][path]=dict(row,sha256=sha(raw),elf_header=raw.startswith(b'\x7fELF'))
            for record in records:
                self.check()
                need(self._python_metadata(record['fd'],'FILE')==record['metadata'] and
                     fs.stamp(os.stat(record['leaf'],dir_fd=record['parent'],follow_symlinks=False))==
                     fs.stamp(record['before']),'RESOURCE_PYTHON_PAIR_FILE_RACE')
                for fd,row in record['ancestors']:
                    need(self._python_metadata(fd,'DIRECTORY')==row,'RESOURCE_PYTHON_PAIR_ANCESTOR_RACE')
            return sample
        finally:
            failures=[]
            for record in reversed(records):
                try:
                    if record['fd'] is not None:os.close(record['fd'])
                except BaseException as exc:failures.append(exc)
                try:self._finish(record['held'],record['links'])
                except BaseException as exc:failures.append(exc)
            if failures:raise failures[0]

    def python_file(self,spec):
        need(set(spec)==FILE_FIELDS|{'python_identity'} and spec['kind']=='FILE' and
             spec['path'] in python_identity.PYTHON_PATHS,'RESOURCE_PYTHON_PAIR_SPEC')
        proof=python_identity.validate_pair_proof(spec['python_identity'])
        wanted=proof['sample']['files'][spec['path']]
        need(all(type(spec[k]) is int and spec[k]==wanted[k] for k in ('uid','gid','mode')) and
             spec['sha256']==wanted['sha256'] and spec['access_acl']==decode_acl(None,wanted['mode']),
             'RESOURCE_PYTHON_PAIR_SPEC_BINDING')
        self.check();before=self._python_pair_sample();after=self._python_pair_sample()
        python_identity.validate_pair_reread(proof,before,after)
        self.check();return copy.deepcopy(spec)

    def node_file(self,spec):
        """One fixed directory alias, checked by the collector's bounded reader."""
        from unit_metadata import validate_node_reference,NODE_CANONICAL_PATH
        from snapshot_io import LocalReadOnlyIO,DescriptorReader
        need(set(spec)==FILE_FIELDS|{'node_reference'} and spec['kind']=='FILE' and
             spec['path']==NODE_CANONICAL_PATH,'RESOURCE_NODE_REFERENCE_SPEC')
        proof=validate_node_reference(spec['node_reference'],spec['path'],spec['sha256'])
        wanted=proof['final']['metadata']
        need(all(type(spec[k]) is int and spec[k]==wanted[k] for k in ('uid','gid','mode')) and
             spec['access_acl']==decode_acl(None,wanted['mode']),'RESOURCE_NODE_REFERENCE_SPEC_BINDING')
        owner=self
        class NodeReadOnlyIO(LocalReadOnlyIO):
            def __init__(self):DescriptorReader.__init__(self,{},root=owner.root)
            def check_locks(self):owner.check()
            def _authority(self,fd,path):return owner._directory(fd,path)
        self.check();actual=NodeReadOnlyIO().node_directory_reference(spec['path'],spec['sha256'])
        need(same_node_reference(actual,proof,self.authority),'RESOURCE_NODE_REFERENCE_DRIFT')
        self.check();return copy.deepcopy(spec)

    def executable_reference(self,proof):
        """Verify an exact measured symlink chain and its canonical ELF inode."""
        need(type(proof) is dict and set(proof)=={'reference_path','links','final'} and
             type(proof['links']) is list and len(proof['links'])<8,'RESOURCE_EXECUTABLE_REFERENCE')
        current=proof['reference_path'];seen=set()
        for link in proof['links']:
            need(type(link) is dict and set(link)=={'path','link','metadata'} and link['path']==current and
                 current not in seen and type(link['link']) is str,'RESOURCE_EXECUTABLE_ALIAS_CHAIN')
            seen.add(current);held,links,parent,leaf=self._parent(current)
            try:
                before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                need(stat.S_ISLNK(before.st_mode) and before.st_nlink==1 and
                     fs.metadata(before)==link['metadata'] and os.readlink(leaf,dir_fd=parent)==link['link'] and
                     fs.stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==fs.stamp(before),
                     'RESOURCE_EXECUTABLE_ALIAS_DRIFT')
            finally:self._finish(held,links)
            current=os.path.normpath(link['link'] if link['link'].startswith('/') else
                                     os.path.join(os.path.dirname(current),link['link']))
        final=proof['final']
        need(type(final) is dict and set(final)=={'path','sha256','format','metadata'} and final['path']==current and
             current not in seen and final['format']=='ELF' and final['metadata']['kind']=='FILE' and
             final['metadata']['sha256']==final['sha256'],'RESOURCE_EXECUTABLE_CANONICAL_ELF')
        meta=final['metadata']
        base_fields=set(python_identity.METADATA_FIELDS)|{'kind','sha256'}
        need(set(meta)==base_fields or ('python_identity' in meta and set(meta) in
             (base_fields|{'python_identity'},set(python_identity.FILE_FIELDS)|{'python_identity'})),
             'RESOURCE_EXECUTABLE_METADATA_FIELDS')
        if 'python_identity' in meta:
            identity=python_identity.validate_pair_proof(meta['python_identity'])
            need(current in python_identity.PYTHON_PATHS and all(
                 type(meta[k]) is type(identity['sample']['files'][current][k]) and
                 meta[k]==identity['sample']['files'][current][k] for k in meta if k!='python_identity'),
                 'RESOURCE_EXECUTABLE_PYTHON_METADATA_BINDING')
        spec={k:meta[k] for k in ('kind','uid','gid','mode','sha256')}
        spec.update(path=current,access_acl=decode_acl(None,meta['mode']))
        if 'python_identity' in meta:spec['python_identity']=copy.deepcopy(meta['python_identity'])
        held,links,parent,leaf=self._parent(current)
        try:
            before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
            need(stat.S_ISREG(before.st_mode) and all(fs.metadata(before)[k]==v for k,v in meta.items()
                 if k in python_identity.METADATA_FIELDS),'RESOURCE_EXECUTABLE_FINAL_IDENTITY')
            self.observe(spec)
            fd=os.open(leaf,fs.READ_FLAGS,dir_fd=parent)
            try:
                need(fs.stamp(os.fstat(fd))==fs.stamp(before) and os.read(fd,4)==b'\x7fELF',
                     'RESOURCE_EXECUTABLE_FINAL_ELF')
            finally:os.close(fd)
            need(fs.stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==fs.stamp(before),
                 'RESOURCE_EXECUTABLE_FINAL_RACE')
        finally:self._finish(held,links)
        return True

    def nss_bindings(self,spec):
        need(set(spec)=={'path','kind','prerequisites','accounts','group_ids','nss_by_primary'} and
             spec['path']=='/etc/passwd' and spec['kind']=='NSS_BINDINGS','RESOURCE_FIXED_NSS_SCOPE')
        need(all(type(spec[k]) is dict and len(spec[k])<=64 for k in
             ('prerequisites','accounts','group_ids','nss_by_primary')),'RESOURCE_NSS_BOUND')
        for name,wanted in spec['prerequisites'].items():
            self.check()
            if name.startswith('group:'):
                row=grp.getgrnam(name[6:]);actual={'gid':row.gr_gid,'members':sorted(row.gr_mem)}
            else:
                need(name.startswith('user:'),'RESOURCE_NSS_PREREQUISITE_KIND')
                row=pwd.getpwnam(name[5:]);actual={'uid':row.pw_uid,'gid':row.pw_gid,
                    'groups':sorted(os.getgrouplist(name[5:],row.pw_gid))}
            need(actual==wanted,'RESOURCE_NSS_PREREQUISITE_DRIFT')
        for name,wanted in spec['accounts'].items():
            self.check();row=pwd.getpwnam(name)
            need({'uid':row.pw_uid,'primary_gid':row.pw_gid,
                  'global_group_gids':sorted(set(os.getgrouplist(name,row.pw_gid)))}==wanted,'RESOURCE_NSS_ACCOUNT_DRIFT')
        for name,gid in spec['group_ids'].items():
            self.check();need(grp.getgrnam(name).gr_gid==gid,'RESOURCE_NSS_NAMED_GROUP_DRIFT')
        for name,pairs in spec['nss_by_primary'].items():
            need(type(pairs) is dict and len(pairs)<=8,'RESOURCE_NSS_PAIR_BOUND')
            for gid,wanted in pairs.items():
                self.check();need(type(gid) is str and gid.isdigit() and str(int(gid))==gid and
                    sorted(set(os.getgrouplist(name,int(gid))))==wanted,'RESOURCE_NSS_PRIMARY_GROUP_DRIFT')
        self.check();return copy.deepcopy(spec)

    def observe(self,spec):
        if type(spec) is dict and 'python_identity' in spec:return self.python_file(spec)
        if type(spec) is dict and 'node_reference' in spec:return self.node_file(spec)
        if type(spec) is dict and spec.get('kind')=='NSS_BINDINGS':return self.nss_bindings(spec)
        if type(spec) is dict and spec.get('kind')=='OPTIONAL_INVENTORY':
            need(set(spec)=={'path','kind','sha256'} and spec['path'] in snap.SCHEDULER_ROOTS,
                 'RESOURCE_FIXED_SCHEDULER_INVENTORY')
            import reviewed_scanner
            self.check();logical=spec['path'];root=(self.root.rstrip('/') if self.root!='/' else '')+logical
            inventory=reviewed_scanner.bounded_file_inventory(root,optional=True)
            if self.root!='/':inventory={k[len(self.root):]:v for k,v in inventory.items()}
            self.check();need(d.digest(inventory)==spec['sha256'],'RESOURCE_SCHEDULER_DRIFT');return copy.deepcopy(spec)
        need(type(spec) is dict and spec.get('kind') in
             ('FILE','MASK','LINK','ABSENT','DIRECTORY','PUBLISHER_FINGERPRINT','TREE_INVENTORY','DATABASE_IDENTITY','JSON_PROJECTION','JSON_OPTIONAL_PROJECTION','JSON_CONTEXT_PROJECTION','JSON_BOUND_PROJECTION','EPOCH_CHAIN','SANDBOX_STABLE'),
             'RESOURCE_SPEC_KIND')
        path=spec['path'];held,links,parent,leaf=self._parent(path)
        fd=None
        try:
            kind=spec['kind']
            if kind=='ABSENT':
                need(set(spec)=={'path','kind'},'RESOURCE_ABSENCE_SPEC')
                before=fs.stamp(os.fstat(parent));names=sorted(os.listdir(parent))
                need(leaf not in names,'RESOURCE_UNEXPECTED_PRESENT')
                try:os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise ValueError('EPOCH7_HOST_RESOURCE_UNEXPECTED_PRESENT')
                need(names==sorted(os.listdir(parent)) and fs.stamp(os.fstat(parent))==before,'RESOURCE_ABSENCE_RACE')
                return {'path':path,'kind':'ABSENT'}
            before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
            if kind=='LINK':
                need(set(spec)=={'path','kind','uid','gid','sha256'} and stat.S_ISLNK(before.st_mode) and
                     before.st_nlink==1,'RESOURCE_LINK_SPEC')
                result={'path':path,'kind':kind,'uid':before.st_uid,'gid':before.st_gid,
                        'sha256':sha(os.readlink(leaf,dir_fd=parent).encode('utf-8'))}
            elif kind=='PUBLISHER_FINGERPRINT':
                need(set(spec)=={'path','kind','uid','gid','dev','ino','sha256'} and path in snap.PUBLISHERS and
                     stat.S_ISDIR(before.st_mode) and all(fs.metadata(before)[k]==spec[k] for k in ('uid','gid','dev','ino')),
                     'RESOURCE_PUBLISHER_IDENTITY')
                import reviewed_publisher
                self.check();digest=reviewed_publisher.fingerprint((self.root.rstrip('/') if self.root!='/' else '')+path,
                    owner_uid=spec['uid'],owner_gid=spec['gid']);self.check()
                result=dict(spec,sha256=digest)
            elif kind=='TREE_INVENTORY':
                need(set(spec)=={'path','kind','sha256'} and stat.S_ISDIR(before.st_mode),'RESOURCE_TREE_SPEC')
                import reviewed_scanner
                self.check();inventory=reviewed_scanner.bounded_file_inventory((self.root.rstrip('/') if self.root!='/' else '')+path)
                if self.root!='/':inventory={k[len(self.root):]:v for k,v in inventory.items()}
                self.check();result={'path':path,'kind':kind,'sha256':d.digest(inventory)}
            elif kind=='MASK':
                need(set(spec)=={'path','kind','uid','gid','link'} and stat.S_ISLNK(before.st_mode)
                     and before.st_nlink==1 and os.readlink(leaf,dir_fd=parent)=='/dev/null','RESOURCE_MASK')
                result={'path':path,'kind':kind,'uid':before.st_uid,'gid':before.st_gid,'link':'/dev/null'}
            else:
                flags=fs.DIR_FLAGS if kind=='DIRECTORY' else fs.READ_FLAGS
                fd=os.open(leaf,flags,dir_fd=parent)
                need(fs.stamp(os.fstat(fd))==fs.stamp(before),'RESOURCE_FILE_OPEN_RACE')
                access=decode_acl(get_attr(fd,ACCESS),stat.S_IMODE(before.st_mode))
                need(get_attr(fd,DEFAULT) is None,'RESOURCE_DEFAULT_ACL')
                if kind=='DIRECTORY':
                    need(set(spec) in ({'path','kind','uid','gid','mode','access_acl','default_acl'},
                                      {'path','kind','uid','gid','mode','dev','ino','access_acl','default_acl'}) and
                         stat.S_ISDIR(before.st_mode),'RESOURCE_DIRECTORY_SPEC')
                    result=dict({k:fs.metadata(before)[k] for k in ('uid','gid','mode','dev','ino') if k in spec},
                                path=path,kind=kind,access_acl=access,default_acl='')
                elif kind=='DATABASE_IDENTITY':
                    need(set(spec)=={'path','kind','uid','gid','mode','dev','ino','nlink','access_acl'} and
                         path==d.DB and stat.S_ISREG(before.st_mode) and before.st_nlink==1,'RESOURCE_CANONICAL_DB')
                    result=dict({k:fs.metadata(before)[k] for k in ('uid','gid','mode','dev','ino','nlink')},
                                path=path,kind=kind,access_acl=access)
                else:
                    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=MAX_BYTES,
                         'RESOURCE_FILE_BOUND')
                    chunks=[];count=0
                    while True:
                        self.check();raw=os.read(fd,min(65536,MAX_BYTES+1-count))
                        if not raw:break
                        chunks.append(raw);count+=len(raw);need(count<=MAX_BYTES,'RESOURCE_FILE_BOUND')
                    need(count==before.st_size,'RESOURCE_READ_SIZE');raw=b''.join(chunks)
                    result={'path':path,'kind':kind,'uid':before.st_uid,'gid':before.st_gid,
                            'mode':stat.S_IMODE(before.st_mode),'access_acl':access}
                    if kind=='FILE':
                        need(set(spec)==FILE_FIELDS,'RESOURCE_FILE_SPEC');digest=sha(raw)
                    elif kind=='EPOCH_CHAIN':
                        need(path==snap.EPOCHS and set(spec)==FILE_FIELDS|{'descriptor','prefix_size','prefix_sha256'},
                             'RESOURCE_EPOCH_CHAIN_SPEC')
                        snap.activation_chain(raw,spec['descriptor'])
                        length=spec['prefix_size'];need(type(length) is int and 0<length<=len(raw) and
                             sha(raw[:length])==spec['prefix_sha256'] and raw[:length].endswith(b'\n'),
                             'RESOURCE_EPOCH7_PREFIX')
                        suffix=[snap.decode(line) for line in raw[length:].splitlines()]
                        state=spec['descriptor']['state'];epoch=spec['descriptor']['epoch']
                        count=0 if epoch==7 else {'PREPARED':1,'QUIESCED':2,'ACTIVE':3}[state]
                        need(epoch in (7,8) and len(suffix)==count,'RESOURCE_OWNED_EPOCH_SUFFIX')
                        if suffix:
                            old=snap.decode(raw[:length].splitlines()[-1])['descriptor']
                            prepared=dict(spec['descriptor'],state='PREPARED')
                            transition=d.controller_transition(old,prepared)
                            wanted={'controller_transition_sha256':d.digest(transition),
                                'approval_body_sha256':self.authority.binding['approval_body_sha256'],
                                'snapshot_sha256':self.authority.context['snapshot_sha256'],
                                'recovery_plan_sha256':self.authority.verifier.wanted['recovery_plan_sha256'],
                                'old_descriptor_sha256':sha(d.canonical(old)+b'\n'),
                                'new_descriptor_sha256':sha(d.canonical(prepared)+b'\n'),
                                'all_writers_excluded':True,'install_lock_held':True,'retained_resources_verified':True,
                                'recovery':'EXACT_EPOCH7_RELEASE_REBIND','writer_admission':False,'previous_epoch':7}
                            need(suffix[0]['proof']==wanted,'RESOURCE_EPOCH_REVIEW_BINDING')
                            if len(suffix)>1:need(suffix[1]['proof']=={k:True for k in
                                ('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited')},
                                'RESOURCE_QUIESCENCE_PROOF')
                            if len(suffix)>2:need(suffix[2]['proof']=={'database_reopened':True},'RESOURCE_ACTIVE_PROOF')
                        result.update(descriptor=copy.deepcopy(spec['descriptor']),prefix_size=length,prefix_sha256=spec['prefix_sha256'])
                        digest=d.digest(spec['descriptor'])
                    elif kind=='SANDBOX_STABLE':
                        need(set(spec)==FILE_FIELDS and path==snap.PROFILE,'RESOURCE_SANDBOX_SCOPE')
                        from p2_sandbox_profile import stable
                        digest=d.digest(stable(raw))
                    else:
                        need(set(spec)==FILE_FIELDS|{'fields'} and type(spec['fields']) is list and
                             1<=len(spec['fields'])<=64,'RESOURCE_JSON_PROJECTION_SPEC')
                        value=snap.decode(raw);selected=[]
                        if kind=='JSON_CONTEXT_PROJECTION':
                            need(value.get('context_sha256')==self.authority.context['context_sha256'],
                                 'RESOURCE_RUNTIME_JOURNAL_CONTEXT')
                        elif kind=='JSON_BOUND_PROJECTION':
                            need(value.get('schema')==1 and value.get('transaction_id')==d.TX and
                                 value.get('name')==path.rsplit('/',1)[1] and
                                 d.same(value.get('binding'),self.authority.binding),'RESOURCE_INNER_JOURNAL_BINDING')
                        for parts in spec['fields']:
                            need(type(parts) is list and 1<=len(parts)<=16 and all(type(p) is str and p for p in parts),
                                 'RESOURCE_JSON_FIELD_PATH')
                            item=value
                            found=True
                            for part in parts:
                                if type(item) is not dict or part not in item:
                                    need(kind=='JSON_OPTIONAL_PROJECTION','RESOURCE_JSON_FIELD_MISSING')
                                    found=False;item=None;break
                                item=item[part]
                            if kind=='JSON_OPTIONAL_PROJECTION':selected.append({'path':parts,'found':found,'value':item})
                            else:selected.append({'path':parts,'value':item})
                        digest=d.digest(selected);result['fields']=copy.deepcopy(spec['fields'])
                    result['sha256']=digest
                need(fs.stamp(os.fstat(fd))==fs.stamp(before),'RESOURCE_FD_READ_RACE')
            need(fs.stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==fs.stamp(before),'RESOURCE_PATH_READ_RACE')
            need(d.same(result,spec),'RESOURCE_EXACT_SPEC_DRIFT')
            return result
        finally:
            if fd is not None:os.close(fd)
            self._finish(held,links)


class CheckpointResources(object):
    """17 exact stable resource projections; raw policies are plan-bound inputs."""
    def __init__(self,context,reader,views,expected_sha256):
        need(isinstance(reader,ResourceReader) and type(views) is list and len(views)==len(PHASES)+1,
             'RESOURCE17_CHECKPOINTS')
        for view in views:
            need(type(view) is dict and set(view)==SECTIONS,'RESOURCE_EXACT_SECTIONS')
            for rows in view.values():
                need(type(rows) is list and 1<=len(rows)<=8192 and
                     len({r['path'] for r in rows})==len(rows),'RESOURCE_FINITE_PATHS')
        d.hash_value(expected_sha256);need(d.digest(views)==expected_sha256,'RESOURCE_VIEW_HASH')
        self.context,self.reader,self.views=copy.deepcopy(context),reader,copy.deepcopy(views)
        self.digest=expected_sha256
    def resources(self,context,phase,boundary,names):
        need(context==self.context and phase in PHASES and boundary in ('before','after','effect') and
             set(names)<=SECTIONS and d.digest(self.views)==self.digest,'RESOURCE_CONTEXT_OR_MUTATION')
        index=PHASES.index(phase)+(1 if boundary=='after' else 0);self.reader.start();result={}
        for name in names:
            result[name]=[self.reader.observe(spec) for spec in self.views[index][name]]
        return result
