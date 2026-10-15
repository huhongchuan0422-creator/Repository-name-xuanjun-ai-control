"""Fresh bounded quiet-start predicates after owned OpenClaw config mutations.

No source/Node execution. Only fixed protected files, absences, NSS and the
selected system-manager environment are observed. Raw secrets are not returned.
"""
import copy
import os
import shlex
import time

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_protected_fs as fs
from epoch7_host_phases import need,sha
from epoch7_resource_observer import same_node_reference
from epoch7_command_runner import ExactCommandRunner
from epoch7_recovery_sequence import PHASES,BoundedDiagnostics
from openclaw_metadata import (GATEWAY,LAUNCHER,RELAY,ENV_KEYS,ABSENT,
                              dotenv_paths,quiet_projection)

BASE='/etc/systemd/system/'+GATEWAY
BACKUP=fs.TRANSACTION+'/'+GATEWAY+'.backup'
RELEASE='/opt/xuanjun-control-releases/integration-'+d.NEW_MANIFEST[:16]


class BoundedQuietStartup(object):
    def __init__(self,policy,authority,census):
        from snapshot_io import LocalReadOnlyIO
        from epoch7_host_observer import LinuxProcessCensus
        need(isinstance(census,LinuxProcessCensus) and isinstance(census.diagnostics,BoundedDiagnostics),
             'QUIET_CONCRETE_CENSUS')
        self.authority,self.census=authority,census
        self.deadline=None;self.phase=None
        self.relay_metadata=None;self.node_reference=None
        owner=self
        class QuietReadOnlyIO(LocalReadOnlyIO):
            def check_locks(self):owner._check()
        self.io=QuietReadOnlyIO(copy.deepcopy(policy),{})

    def bind_resource_views(self,views):
        """Bind service-readable relay metadata from the approved checkpoints."""
        need(self.relay_metadata is None and type(views) is list and len(views)==17,
             'QUIET_REVIEWED_RESOURCE_VIEWS')
        values=[]
        for view in views:
            rows=[row for section in view.values() for row in section if row.get('path')==RELAY]
            need(len(rows)==1 and rows[0].get('kind')=='FILE','QUIET_RELAY_RESOURCE_COVERAGE')
            value={key:rows[0][key] for key in ('uid','gid','mode')}
            need(all(type(item) is int and item>=0 for item in value.values()) and
                 value['uid']==0 and value['mode']<=0o777 and not value['mode']&0o022,
                 'QUIET_RELAY_RESOURCE_AUTHORITY')
            values.append(value)
        need(all(value==values[0] for value in values),'QUIET_RELAY_METADATA_TRANSITION')
        self.relay_metadata=copy.deepcopy(values[0])
        from unit_metadata import validate_node_reference,NODE_CANONICAL_PATH
        references=[]
        for view in views:
            rows=[row for section in view.values() for row in section if 'node_reference' in row]
            need(len(rows)<=1,'QUIET_NODE_REFERENCE_UNIQUE')
            if not rows:references.append(None);continue
            row=rows[0]
            need(row.get('kind')=='FILE' and row['path']==NODE_CANONICAL_PATH,'QUIET_NODE_REFERENCE_SCOPE')
            references.append(validate_node_reference(row['node_reference'],row['path'],row['sha256']))
        need(all(item==references[0] for item in references),'QUIET_NODE_REFERENCE_TRANSITION')
        self.node_reference=copy.deepcopy(references[0])

    def _check(self):
        self.authority.receipt()
        need(self.deadline is not None and time.monotonic()<self.deadline,'QUIET_SHARED_GUARD_DEADLINE')

    @staticmethod
    def selected_environment(raw):
        need(type(raw) is bytes and len(raw)<=65536,'QUIET_MANAGER_OUTPUT_BOUND')
        values={name:None for name in ENV_KEYS};seen=set()
        for line in raw.decode('utf-8','strict').splitlines():
            name,sep,unused=line.partition('=')
            if name not in values:continue
            need(sep and name not in seen and len(line)<=4096,'QUIET_MANAGER_ENV_FIELDS');seen.add(name)
            parsed=shlex.split(line)
            need(len(parsed)==1 and parsed[0].startswith(name+'='),'QUIET_MANAGER_ENV_SYNTAX')
            values[name]=parsed[0][len(name)+1:]
        return values

    def _environment(self):
        self._check();need(self.census.executable('/usr/bin/systemctl') is True,'QUIET_SYSTEMCTL_PIN')
        remaining=int(self.deadline-time.monotonic());need(remaining>=1,'QUIET_QUERY_DEADLINE')
        spec={'phase':self.phase,'operation':'service_show','argv':['/usr/bin/systemctl','show-environment'],
              'cwd':'/','env':{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},
              'timeout':min(5,remaining),'accepted_returncodes':[0]}
        def guard():self._check();return True
        raw=ExactCommandRunner({'selected_environment':spec},guard,self.census.diagnostics).run('selected_environment').stdout
        need(self.census.executable('/usr/bin/systemctl') is True,'QUIET_SYSTEMCTL_AFTER_PIN')
        return self.selected_environment(raw)

    def observe(self,blocks,phase,deadline):
        from unit_metadata import UNITS
        from epoch7_openclaw_recipe import validate_quiet_startup
        need(phase in PHASES and type(blocks) is dict and GATEWAY in blocks,'QUIET_REVIEWED_SCOPE')
        wanted=validate_quiet_startup(blocks[GATEWAY]['quiet_startup'])
        need(all(block['quiet_startup']==wanted for block in blocks.values()),'QUIET_SHARED_PROFILE')
        need(self.relay_metadata is not None,'QUIET_RELAY_METADATA_NOT_BOUND')
        self.phase,self.deadline=phase,deadline;self.io.deadline=deadline;self._check()
        manager=self.census._manager();need(manager==self.census.manager_pin,'QUIET_MANAGER_IDENTITY')
        selected=self._environment();account=self.io.gateway_account_home()
        captures={};absences=set()
        def read(path,maximum,owner,expected=None):
            self._check();raw,row=self.io.read(path,maximum=maximum)
            authority=(all(row[key]==value for key,value in expected.items()) if expected is not None
                       else row['uid']==owner and (owner!=0 or row['gid']==0))
            need(row['kind']=='FILE' and authority and row['nlink']==1 and
                 not row['mode']&0o7022,'QUIET_FILE_AUTHORITY')
            captures[path]=(raw,row,maximum);return raw
        def absent(path):
            self._check();need(self.io.absent(path) is True,'QUIET_REQUIRED_ABSENCE');absences.add(path)
        # The only pre-restoration alternative is the exact protected backup.
        try:mask=self.io.mask(BASE)
        except (FileNotFoundError,OSError,ValueError):
            unit_raw=read(BASE,65536,0);masked=False
        else:
            need(mask['kind']=='MASK' and mask['link']=='/dev/null','QUIET_GATEWAY_MASK')
            unit_raw=read(BACKUP,65536,0);masked=True
        need(sha(unit_raw)==blocks[GATEWAY]['sources'][BASE],'QUIET_UNIT_SOURCE_PIN')
        wrapper=read(LAUNCHER,65536,1002)
        need(sha(wrapper)==blocks[GATEWAY]['sources'][LAUNCHER],'QUIET_WRAPPER_SOURCE_PIN')
        identity=blocks[GATEWAY]['roles'][0]['identity'];node=identity['executable']
        from epoch7_openclaw_recipe import DIRECT_WRAPPER_SHA
        reference=None
        if sha(wrapper)==DIRECT_WRAPPER_SHA:
            from unit_metadata import validate_node_reference
            reference=validate_node_reference(self.node_reference,node,identity['executable_sha256'])
            need(blocks[GATEWAY]['sources'].get(node)==identity['executable_sha256'],
                 'QUIET_NODE_SOURCE_PIN')
            need(same_node_reference(self.io.node_directory_reference(node,identity['executable_sha256']),reference,self.authority),
                 'QUIET_NODE_REFERENCE_DRIFT')
        else:need(self.node_reference is None,'QUIET_ROOT_NODE_REFERENCE_FORBIDDEN')
        profile=read(snap.PROFILE,1048576,1002);relay=read(RELAY,65536,0,self.relay_metadata)
        inventory=self.io.unit_dropins(UNITS);raws=[]
        need(set(inventory)==set(UNITS),'QUIET_COMPLETE_DROPIN_SCOPE')
        for roots in inventory.values():
            need(all(type(row.get('present')) is bool and row.get('state')!='UNKNOWN' for row in roots.values()),
                 'QUIET_UNKNOWN_DROPIN_ROOT')
        for root,item in sorted(inventory[GATEWAY].items()):
            for path,(raw,row) in sorted(item['files'].items()):
                need(row['uid']==row['gid']==0 and row['nlink']==1,'QUIET_DROPIN_AUTHORITY')
                captures[path]=(raw,row,65536);raws.append(raw)
        dotenv={}
        for path in dotenv_paths(unit_raw):
            if self.io.absent(path):absent(path);dotenv[path]=None
            else:dotenv[path]=read(path,65536,0 if path=='/.env' else 1002)
        for name in ABSENT:absent(wanted['package_root']+'/'+name)
        # Relay executes from the sealed release stage1, not the collector cwd.
        if phase not in ('stage_exact_release',):absent(RELEASE+'/stage1/.env')
        projected=quiet_projection(selected,account,unit_raw,wrapper,node,profile,dotenv,relay,raws,
            node_reference=reference,node_sha256=identity.get('executable_sha256') if reference is not None else None)
        actual={'schema':1,'package_root':wanted['package_root'],
            'package_absence':{name:'ABSENT' for name in ABSENT}}
        actual.update({key:projected[key] for key in
            ('selected_environment','config_projection','node_exec_argv','relay_environment')})
        need(actual==wanted,'QUIET_REVIEWED_PROJECTION_DRIFT')
        for path,(raw,row,maximum) in sorted(captures.items()):
            self._check();need(self.io.read(path,maximum=maximum)==(raw,row),'QUIET_LATE_FILE_RACE')
        for path in sorted(absences):self._check();need(self.io.absent(path) is True,'QUIET_LATE_ABSENCE_RACE')
        if reference is not None:
            need(same_node_reference(self.io.node_directory_reference(node,identity['executable_sha256']),reference,self.authority),
                 'QUIET_LATE_NODE_REFERENCE_DRIFT')
        if masked:need(self.io.mask(BASE)==mask,'QUIET_LATE_MASK_RACE')
        need(self.io.unit_dropins(UNITS)==inventory,'QUIET_LATE_DROPIN_RACE')
        need(self.io.gateway_account_home()==account and self._environment()==selected and
             self.census._manager()==manager,'QUIET_LATE_ENVIRONMENT_RACE')
        self._check();return actual
