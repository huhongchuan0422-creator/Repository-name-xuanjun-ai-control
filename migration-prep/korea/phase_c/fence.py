"""One exact root-admitted NEW dedicated nft table plus four negative probes.

Only loopback TCP connects, no payload/provider/DNS/credential/DB/service start.
No global flush, chain policy update, deletion, cleanup or automatic retry.
A partially installed table remains restricting only the two dedicated idle UIDs.
This source does not authorize a host command; synthetic tests do not prove kernel
enforcement. The complete C package still needs independent approval and root.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

from gate_common import canonical_bytes, require
from korea.phase_c import artifact
from korea.phase_c.authorization import HOST
from korea.phase_c.entry import load_config
from korea.phase_c.install_controller import atomic_receipt, frozen_b, SHARED, UNITS
from korea.phase_c.lifecycle import (Context as LiveContext, CONFIG, NETWORK_PROOF, nft_shape,
                                    temporary_objects)
from korea.phase_c.network import compile_rules, validate_policy
from korea.phase_c.security import digest, fsync_dir, hash_value, read_file, strict_json, trusted_directory, write_once

ACTION='PR99_PHASE_C_DEDICATED_NETWORK_PREFLIGHT_V1'
MARKER='PR99_PHASE_C_FENCE_APPROVAL_V1'
PIN='/etc/xuanjun-pr99-release/phase-c-network-admission.json'
WORK='/var/lib/xuanjun-pr99-phase-c-network-v1'
LOCK='/run/xuanjun-pr99-phase-c-network.lock'
PROBE_CODE='''import json,os,socket,sys
uid=int(sys.argv[1]);family=sys.argv[2]
os.setgroups([]);os.setgid(uid);os.setuid(uid)
assert os.getuid()==os.geteuid()==uid
address="127.0.0.1" if family=="IPv4" else "::1"
s=socket.socket(socket.AF_INET if family=="IPv4" else socket.AF_INET6,socket.SOCK_STREAM)
s.settimeout(0.5);connected=False
try:s.connect((address,9));connected=True
except OSError:pass
finally:s.close()
print(json.dumps(dict(uid=os.geteuid(),family=family,address=address,connected=connected),sort_keys=True))
'''


def verify_pin(pin,expected,now):
    require(type(pin) is dict and set(pin)=={'approval_comment_id','approval_body_sha256','approval_body'} and
            type(pin['approval_comment_id']) is int and pin['approval_comment_id']>0 and
            type(pin['approval_body']) is str and 0<len(pin['approval_body'].encode())<=100000 and
            digest(pin['approval_body'].encode())==pin['approval_body_sha256'],'C_FENCE_ROOT_PIN')
    b,e='<!-- '+MARKER+'\n','\n'+MARKER+' -->';body=pin['approval_body']
    require(body.count(b)==body.count(e)==1 and body.index(b)<body.index(e),'C_FENCE_APPROVAL_MARKER')
    a=strict_json(body.split(b)[1].split(e)[0])
    fixed=dict(expected,schema_version=1,decision='APPROVED_WITH_EXACT_PRECONDITIONS',host=HOST,action=ACTION,
        max_attempts=1,network_changes_allowed=True,loopback_negative_probes_allowed=True,service_start_allowed=False,
        credentials_allowed=False,database_export_allowed=False,writer_allowed=False)
    require(set(a)==set(fixed)|{'approval_comment_id','issued_at','expires_at'},'C_FENCE_APPROVAL_FIELDS')
    for k,v in fixed.items():require(type(a[k]) is type(v) and a[k]==v,'C_FENCE_APPROVAL_SCOPE')
    require(type(a['approval_comment_id']) is int and a['approval_comment_id']==pin['approval_comment_id'] and
            type(a['issued_at']) is int and type(a['expires_at']) is int and a['issued_at']<=now<a['expires_at'] and
            0<a['expires_at']-a['issued_at']<=43200,'C_FENCE_APPROVAL_TIME')
    return a


def other_tables(value, table):
    require(type(value) is dict and set(value)=={'nftables'} and type(value['nftables']) is list,'C_FENCE_GLOBAL_JSON')
    result=[]
    for row in value['nftables']:
        require(type(row) is dict and len(row)==1,'C_FENCE_GLOBAL_ROW')
        kind=next(iter(row))
        if kind=='metainfo':continue
        body=row[kind]
        require(type(body) is dict,'C_FENCE_GLOBAL_OBJECT')
        if body.get('family')=='inet' and (body.get('table')==table or kind=='table' and body.get('name')==table):continue
        result.append(row)
    return {'nftables':result}


def drop_counter(table, name, uid):
    found=[]
    for row in table['nftables']:
        rule=row.get('rule')
        if not rule or rule.get('family')!='inet' or rule.get('table')!=name or rule.get('chain')!='output':continue
        expr=rule.get('expr',[])
        if len(expr)!=3 or expr[-1]!={'drop':None}:continue
        if expr[0]!={'match':{'op':'==','left':{'meta':{'key':'skuid'}},'right':uid}}:continue
        counter=expr[1].get('counter')
        require(type(counter) is dict and set(counter)=={'packets','bytes'} and
                all(type(v) is int and v>=0 for v in counter.values()),'C_FENCE_DROP_COUNTER')
        found.append(counter['packets'])
    require(len(found)==1,'C_FENCE_EXACT_UID_DROP_COUNTER_REQUIRED')
    return found[0]


class Context(LiveContext):
    def nft(self,args,data=None):
        # Separate stdin-only path; neither command text nor rule input is a shell.
        program=Path('/usr/sbin/nft').resolve(strict=True);trusted_directory(program.parent)
        s=program.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'C_FENCE_NFT_PROGRAM')
        r=subprocess.run(['/usr/sbin/nft',*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'},timeout=10)
        require(len(r.stdout.encode())+len(r.stderr.encode())<=4*1024*1024,'C_FENCE_OUTPUT_BOUND')
        return r
    def table(self,name):
        r=self.nft(['-j','list','table','inet',name]);require(r.returncode==0,'C_FENCE_TABLE_UNAVAILABLE')
        return strict_json(r.stdout)
    def global_rules(self):
        r=self.nft(['-j','-s','list','ruleset']);require(r.returncode==0,'C_FENCE_GLOBAL_UNAVAILABLE')
        return strict_json(r.stdout)
    def probe(self,uid,family):
        program=Path('/usr/bin/python3.11').resolve(strict=True);trusted_directory(program.parent)
        s=program.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'C_FENCE_PYTHON_IDENTITY')
        r=subprocess.run(['/usr/bin/python3.11','-I','-B','-c',PROBE_CODE,str(uid),family],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=3,
            env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
        require(r.returncode==0 and len(r.stdout)<=1024,'C_FENCE_PROBE_UNKNOWN')
        row=strict_json(r.stdout)
        require(row==dict(uid=uid,family=family,address='127.0.0.1' if family=='IPv4' else '::1',connected=False),
                'C_FENCE_PROBE_CONNECTED_OR_IDENTITY')
        return row


def apply_once(ctx=None):
    ctx=ctx or Context();ctx.check_identity()
    config=load_config(ctx.path(CONFIG));policy=config['network_policy'];validate_policy(policy,ctx.now_ms())
    release=ctx.path('/opt/xuanjun-binance-phase-c/releases/'+config['runtime_manifest_sha256'])
    ctx.verify_loaded(release,config['runtime_manifest_sha256'])
    pin_raw=read_file(ctx.path(PIN),modes=(0o600,),limit=110000)
    trusted_directory(ctx.path(PIN).parent,exact_mode=0o700)
    pin=strict_json(pin_raw)
    a=verify_pin(pin,dict(runtime_manifest_sha256=config['runtime_manifest_sha256'],config_sha256=hash_value(config),
        policy_sha256=hash_value(policy),controller_sha256=digest(read_file(release/(artifact.PREFIX+'fence.py'),modes=(0o444,),limit=1048576))),ctx.now())
    require(ctx.current_approval(a['approval_comment_id'])==pin['approval_body'],'C_FENCE_CURRENT_APPROVAL')
    before=frozen_b(ctx);shared=ctx.units(SHARED);ctx.quiescent(config)
    require(all(v['ActiveState']=='inactive' and v['MainPID']=='0' for v in ctx.states().values()),'C_FENCE_CANDIDATE_ACTIVE')
    require(ctx.units((UNITS['network-verified.target'],))[UNITS['network-verified.target']]['ActiveState']=='inactive',
            'C_FENCE_TARGET_ACTIVE')
    for name in (WORK,LOCK,NETWORK_PROOF):
        require(not os.path.lexists(ctx.path(name)),'C_FENCE_EXISTING_ATTEMPT_OR_PROOF')
        trusted_directory(ctx.path(name).parent)
    global_before=ctx.global_rules()
    require(not any(row.get('table',{}).get('family')=='inet' and row['table'].get('name')==policy['table']
                    for row in global_before['nftables']),'C_FENCE_TABLE_ALREADY_EXISTS')
    rules=compile_rules(policy,ctx.now_ms())
    require(ctx.nft(['-c','-f','-'],rules).returncode==0,'C_FENCE_SYNTAX_FAILED')
    require(read_file(ctx.path(PIN),modes=(0o600,),limit=110000)==pin_raw and
            ctx.current_approval(a['approval_comment_id'])==pin['approval_body'] and ctx.now()<a['expires_at'],
            'C_FENCE_AUTHORITY_CHANGED_BEFORE_CLAIM')
    work=ctx.path(WORK);work.mkdir(mode=0o700);os.chmod(work,0o700);fsync_dir(work.parent)
    receipt=dict(schema_version=1,action=ACTION,status='PREPARING',approval_comment_id=a['approval_comment_id'],
        network_apply_attempted=False,service_started=False,credentials_read=False,database_opened=False,
        writer_enabled=False,retry_allowed=False)
    lock=ctx.path(LOCK);identity=None
    def save():atomic_receipt(work/'receipt.json',receipt)
    try:
        save();lock.mkdir(mode=0o700);os.chmod(lock,0o700);fsync_dir(lock.parent)
        s=lock.lstat();identity=(s.st_dev,s.st_ino)
        write_once(work/'consumed-approval.json',pin_raw);write_once(work/'candidate.nft',rules.encode())
        write_once(work/'global-before.json',canonical_bytes(global_before))
        # Recheck absence, protected state and idle identities immediately before the single load.
        require(ctx.global_rules()==global_before and frozen_b(ctx)==before and ctx.units(SHARED)==shared,
                'C_FENCE_PRESTATE_DRIFT')
        ctx.quiescent(config);require(ctx.now()<a['expires_at'],'C_FENCE_APPROVAL_EXPIRED_BEFORE_APPLY')
        validate_policy(policy,ctx.now_ms())
        receipt['network_apply_attempted']=True;save()
        require(ctx.nft(['-f','-'],rules).returncode==0,'C_FENCE_APPLY_UNKNOWN')
        table=ctx.table(policy['table']);shape=hash_value(nft_shape(table));probes=[]
        for uid in (986,policy['worker_uid']):
            for family in ('IPv4','IPv6'):
                require(ctx.now()<a['expires_at'],'C_FENCE_APPROVAL_EXPIRED_DURING_PROBES')
                before_counter=drop_counter(ctx.table(policy['table']),policy['table'],uid)
                ctx.probe(uid,family)
                after_table=ctx.table(policy['table'])
                require(hash_value(nft_shape(after_table))==shape,'C_FENCE_SHAPE_DRIFT')
                delta=drop_counter(after_table,policy['table'],uid)-before_counter
                require(delta>0,'C_FENCE_NO_KERNEL_DROP_EVIDENCE')
                probes.append(dict(uid=uid,family=family,connected=False,drop_counter_delta=delta))
        ctx.quiescent(config)
        global_after=ctx.global_rules()
        require(other_tables(global_after,policy['table'])==other_tables(global_before,policy['table']) and
                frozen_b(ctx)==before and ctx.units(SHARED)==shared,'C_FENCE_SHARED_OR_GLOBAL_CHANGED')
        validate_policy(policy,ctx.now_ms())
        proof=dict(schema_version=1,host=HOST,policy_sha256=hash_value(policy),table_shape_sha256=shape,
            observed_at_ms=ctx.now_ms(),expires_at_ms=policy['expires_at_ms'],negative_probes=probes,
            root_evidence_id='network-'+str(a['approval_comment_id']))
        # This private proof is genuine controller output ONLY after kernel counters.
        # It still needs its exact hash in the independently approved live plan.
        write_once(ctx.path(NETWORK_PROOF),canonical_bytes(proof))
        write_once(work/'global-after.json',canonical_bytes(global_after))
        s=lock.lstat();require((s.st_dev,s.st_ino)==identity and stat.S_ISDIR(s.st_mode) and s.st_uid==0 and
            stat.S_IMODE(s.st_mode)==0o700 and not list(lock.iterdir()),'C_FENCE_LOCK_CHANGED')
        lock.rmdir();fsync_dir(lock.parent)
        receipt.update(status='DEDICATED_FENCE_KERNEL_NEGATIVE_PROBES_PASS',proof_sha256=hash_value(proof),lock_released=True)
        save();return receipt
    except BaseException as error:
        receipt.update(status='HOLD_PRESERVE_EVIDENCE',error_type=type(error).__name__,
                       error=str(error) if type(error).__name__=='GateError' else 'BOUNDED_FAILURE')
        save();raise


def main():
    argparse.ArgumentParser().parse_args();os.umask(0o077)
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(RuntimeError('SIGTERM')))
    try:result=apply_once();print(json.dumps(result,sort_keys=True));return 0
    except BaseException as error:
        print(json.dumps({'status':'HOLD_PRESERVE_EVIDENCE','error_type':type(error).__name__,'retry_allowed':False}));return 2


if __name__=='__main__':sys.exit(main())
