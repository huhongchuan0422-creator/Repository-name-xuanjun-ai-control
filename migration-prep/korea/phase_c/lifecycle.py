"""Root supervision of one PREPARED and independently admitted readonly window.

This controller does NOT provision custody, transfer identities or firewall
rules. Missing actual root preflight evidence stops before any service action.
No source SecretRef is revoked; only this exact temporary pair and broker key
are quarantined after both dedicated UIDs are proved quiescent. The quarantine
and all evidence persist; there is no automatic restart/second window.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

from gate_common import canonical_bytes, require
from korea.phase_c import artifact
from korea.phase_c.authorization import HOST
from korea.phase_c.credentials import load_pair
from korea.phase_c.entry import load_config
from korea.phase_c.install_controller import (Context as InstallContext, SHARED, UNITS,
    WORK as INSTALL_WORK, frozen_b, atomic_receipt)
from korea.phase_c.runtime import verify_admission
from korea.phase_c.prepare import render_units
from korea.phase_c.security import (DetachedRSA, digest, fsync_dir, hash_value, identifier, read_file,
    rename_new, strict_json, trusted_directory, write_once)
from korea.phase_c.snapshots import pin_current
from korea.shadow_acceptance import _finalize, _tested_object

ACTION = "PR99_PHASE_C_SUPERVISE_PREPARED_READONLY_WINDOW_V1"
MARKER = "PR99_PHASE_C_LIFECYCLE_APPROVAL_V1"
PIN = "/etc/xuanjun-pr99-release/phase-c-lifecycle-admission.json"
WORK = "/var/lib/xuanjun-pr99-phase-c-live-v1"
LOCK = "/run/xuanjun-pr99-phase-c-live.lock"
CONFIG = "/etc/xuanjun-binance-phase-c/runtime.json"
NETWORK_PROOF = "/etc/xuanjun-pr99-release/phase-c-network-proof.json"
REVOKE = "/etc/xuanjun-pr99-release/phase-c-revoke"
QUARANTINE = "/run/xuanjun-phase-c-quarantine-v1"


def approval(pin, expected, now):
    require(type(pin) is dict and set(pin) == {"approval_comment_id", "approval_body_sha256", "approval_body"}
            and type(pin["approval_comment_id"]) is int and pin["approval_comment_id"] > 0 and
            type(pin["approval_body"]) is str and 0 < len(pin["approval_body"].encode()) <= 100000 and
            digest(pin["approval_body"].encode()) == pin["approval_body_sha256"], "C_LIVE_ROOT_PIN")
    body = pin["approval_body"]
    begin, end = "<!-- " + MARKER + "\n", "\n" + MARKER + " -->"
    require(body.count(begin) == body.count(end) == 1 and body.index(begin) < body.index(end),
            "C_LIVE_APPROVAL_MARKER")
    value = strict_json(body.split(begin)[1].split(end)[0])
    fixed = dict(expected, schema_version=1, decision="APPROVED_WITH_EXACT_PRECONDITIONS",
        host=HOST, action=ACTION, max_attempts=1, service_start_allowed=True, service_stop_allowed=True,
        temporary_quarantine_allowed=True, credential_validation_allowed=True, network_changes_allowed=False,
        database_export_allowed=False, writer_allowed=False)
    require(set(value) == set(fixed) | {"approval_comment_id", "issued_at", "expires_at"}, "C_LIVE_APPROVAL_FIELDS")
    for key, expected_value in fixed.items():
        require(type(value[key]) is type(expected_value) and value[key] == expected_value, "C_LIVE_APPROVAL_SCOPE")
    require(type(value["approval_comment_id"]) is int and value["approval_comment_id"] == pin["approval_comment_id"] and
            type(value["issued_at"]) is int and type(value["expires_at"]) is int and
            value["issued_at"] <= now < value["expires_at"] and
            0 < value["expires_at"] - value["issued_at"] <= 7 * 86400, "C_LIVE_APPROVAL_TIME")
    return value


def nft_shape(value):
    """Keep every semantic field; exclude only changing counters/handle metadata.

    The precise result hash is pinned by separately approved ROOT network proof,
    not generated from a config boolean or a self-signed application receipt.
    """
    require(type(value) is dict and set(value) == {"nftables"} and type(value["nftables"]) is list,
            "C_LIVE_NFT_JSON")
    def clean(node):
        if type(node) is list:
            return [clean(x) for x in node]
        if type(node) is dict:
            out = {}
            for key, item in node.items():
                if key == "counter":
                    require(type(item) is dict and set(item) <= {"packets", "bytes"} and
                            all(type(v) is int and v >= 0 for v in item.values()), "C_LIVE_COUNTER")
                    out[key] = {}
                else:
                    out[key] = clean(item)
            return out
        return node
    rows=[]
    for row in value['nftables']:
        require(type(row) is dict and len(row)==1,'C_LIVE_NFT_ROW')
        kind=next(iter(row))
        if kind=='metainfo':continue
        require(kind in ('table','chain','rule') and type(row[kind]) is dict,'C_LIVE_NFT_KIND')
        body=dict(row[kind]);body.pop('handle',None)  # only object metadata, never expression fields
        rows.append({kind:clean(body)})
    return {'nftables':rows}


def network_proof(value, config, now_ms):
    fields = {"schema_version", "host", "policy_sha256", "table_shape_sha256", "observed_at_ms",
              "expires_at_ms", "negative_probes", "root_evidence_id"}
    require(type(value) is dict and set(value) == fields and value["schema_version"] == 1 and
            value["host"] == HOST and value["policy_sha256"] == hash_value(config["network_policy"]) and
            type(value["observed_at_ms"]) is int and type(value["expires_at_ms"]) is int and
            value["observed_at_ms"] <= now_ms < value["expires_at_ms"] and
            value["expires_at_ms"] - value["observed_at_ms"] <= 7 * 86400000,
            "C_LIVE_NETWORK_PROOF")
    identifier(value["root_evidence_id"])
    require(type(value["table_shape_sha256"]) is str and len(value["table_shape_sha256"]) == 64 and
            all(c in "0123456789abcdef" for c in value["table_shape_sha256"]), "C_LIVE_NFT_SHAPE_PIN")
    expected = {(uid, family) for uid in (986, config["network_policy"]["worker_uid"])
                for family in ("IPv4", "IPv6")}
    rows = value["negative_probes"]
    require(type(rows) is list and len(rows) == 4, "C_LIVE_NEGATIVE_PROBES_REQUIRED")
    actual = set()
    for row in rows:
        require(type(row) is dict and set(row) == {"uid", "family", "drop_counter_delta", "connected"} and
                type(row["uid"]) is int and type(row["drop_counter_delta"]) is int and
                row["drop_counter_delta"] > 0 and row["connected"] is False,
                "C_LIVE_NEGATIVE_PROBE_FAILED")
        actual.add((row["uid"], row["family"]))
    require(actual == expected, "C_LIVE_NEGATIVE_PROBE_SCOPE")


class Context(InstallContext):
    def now_ms(self): return int(self.now() * 1000)
    def sleep(self, seconds): time.sleep(seconds)
    def temporary_objects(self, config): return temporary_objects(self, config)

    def verify_loaded(self, release, manifest_sha):
        artifact.verify_runtime(release, manifest_sha)
        origin = Path(__file__).resolve().parents[3]
        trusted_directory(origin)
        for name in artifact.RUNTIME_FILES:
            require(read_file(origin / name, modes=(0o400, 0o444, 0o644), limit=1048576) ==
                    read_file(release / name, modes=(0o444,), limit=1048576), "C_LIVE_EXECUTING_SOURCE")

    def verify_installed(self, installed, config):
        raw=read_file(self.path(INSTALL_WORK)/'input-plan.json',modes=(0o600,))
        require(digest(raw)==installed['plan_sha256'],'C_LIVE_INSTALL_PLAN_PIN')
        plan=strict_json(raw)
        require(plan['runtime_config']==config,'C_LIVE_INSTALLED_CONFIG_DRIFT')
        for name,data in render_units(plan['render_values']).items():
            require(read_file(self.path('/etc/systemd/system')/UNITS[name],modes=(0o644,))==data.encode(),
                    'C_LIVE_INSTALLED_UNIT_DRIFT')
        return plan['acceptance_config']

    def table_shape(self, table):
        r = self.run(["/usr/sbin/nft", "-j", "list", "table", "inet", identifier(table)])
        require(r.returncode == 0, "C_LIVE_NFT_TABLE_UNAVAILABLE")
        return hash_value(nft_shape(strict_json(r.stdout)))

    def states(self):
        names = [UNITS["worker.service"], UNITS["broker.service"]]
        r = self.run(["/usr/bin/systemctl", "show", *names, "--no-pager", "-p", "Id", "-p", "ActiveState",
                      "-p", "SubState", "-p", "MainPID", "-p", "Result", "-p", "ExecMainStatus", "-p", "ControlGroup"])
        require(r.returncode == 0, "C_LIVE_SERVICE_METADATA")
        rows = [dict(line.split("=", 1) for line in block.splitlines()) for block in r.stdout.strip().split("\n\n")]
        require(len(rows) == 2 and {row["Id"] for row in rows} == set(names), "C_LIVE_SERVICE_IDENTITIES")
        return {row["Id"]: row for row in rows}

    def quiescent(self, config):
        identity = self.account_preflight(config["network_policy"]["worker_uid"], config["snapshot_reader_uid"])
        require(identity["create_worker"] is False, "C_LIVE_WORKER_MISSING")

    def verify_custody_and_snapshot(self, config, now_ms, expires_ms):
        expected = {"role": config["credential_role"], "account_id": config["account_id"], "secret_ref": config["secret_ref"]}
        verifier = lambda record: hash_value(record) == config["custody_attestation_sha256"]
        # Scope explicitly requires credential validation; values never leave memory or enter receipts.
        pair = load_pair(config["credential_generation"], expected, verifier, now_ms)
        del pair
        a = strict_json(read_file(self.path(config["credential_generation"]) / "custody.json", modes=(0o444,)))
        require(a["expires_at_ms"] >= expires_ms, "C_LIVE_CUSTODY_WINDOW")
        signer = DetachedRSA(config["broker_public_key"], config["broker_public_key_sha256"],
                             private_key=config["broker_private_key"], key_owner=986)
        challenge = {"purpose": "C_LIVE_KEY_PAIR_CHECK", "config_sha256": hash_value(config)}
        require(signer.verify(challenge, signer.sign(challenge)), "C_LIVE_BROKER_KEY_MISMATCH")
        source = DetachedRSA(config["source_public_key"], config["source_public_key_sha256"])
        _, _, held = pin_current(config["snapshot_root"], config, source, now_ms)
        held.close()

    def read_window(self, config, acceptance):
        parent = self.path(config["evidence_root"])
        trusted_directory(parent.parent)
        s = parent.lstat()
        uid = config["network_policy"]["worker_uid"]
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == uid and stat.S_IMODE(s.st_mode) == 0o700,
                "C_LIVE_EVIDENCE_PARENT")
        fd = os.open(parent / ("shadow-window-" + identifier(acceptance["window_id"]) + ".json"),
                     os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == uid and before.st_nlink == 1 and
                    stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= 16 * 1024 * 1024,
                    "C_LIVE_WINDOW_IDENTITY")
            raw = bytearray()
            while len(raw) < before.st_size:
                block = os.read(fd, min(65536, before.st_size - len(raw)))
                require(bool(block), "C_LIVE_WINDOW_TRUNCATED"); raw.extend(block)
            after = os.fstat(fd)
            require(all(getattr(before,k) == getattr(after,k) for k in
                        ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")), "C_LIVE_WINDOW_CHANGED")
            return strict_json(raw)
        finally: os.close(fd)


def temporary_objects(ctx, config):
    require(config["credential_generation"].startswith("/run/xuanjun-phase-c-credentials/") and
            len(Path(config["credential_generation"]).parts) == 4 and
            config["broker_private_key"] == "/run/xuanjun-phase-c-private-keys/broker.pem",
            "C_LIVE_TEMPORARY_SCOPE")
    objects = {}
    for name in (config["credential_generation"], config["broker_private_key"]):
        path = ctx.path(name); trusted_directory(path.parent)
        s = path.lstat()
        if name == config["credential_generation"]:
            trusted_directory(path, exact_mode=0o711)
            require(set(p.name for p in path.iterdir()) == {"api_key", "api_secret", "custody.json"},
                    "C_LIVE_TEMP_PAIR_FILE_SET")
        else:
            require(stat.S_ISREG(s.st_mode) and s.st_uid == 986 and s.st_nlink == 1 and
                    stat.S_IMODE(s.st_mode) == 0o400, "C_LIVE_TEMPORARY_KEY")
        objects[name] = (s.st_dev, s.st_ino)
    return objects


def supervise(plan_path, ctx=None):
    ctx = ctx or Context()
    ctx.check_identity()
    config = load_config(ctx.path(CONFIG))
    release = ctx.path("/opt/xuanjun-binance-phase-c/releases/" + config["runtime_manifest_sha256"])
    ctx.verify_loaded(release, config["runtime_manifest_sha256"])
    plan_raw = read_file(plan_path, modes=(0o400,0o600), limit=65536)
    plan = strict_json(plan_raw)
    require(type(plan) is dict and set(plan) == {"acceptance", "signed_admission", "network_proof_sha256",
                "installed_receipt_sha256", "stop_grace_seconds"} and plan["stop_grace_seconds"] == 30,
            "C_LIVE_PLAN_FIELDS")
    trusted_directory(ctx.path(PIN).parent, exact_mode=0o700)
    pin_raw = read_file(ctx.path(PIN), modes=(0o600,), limit=110000)
    pin = strict_json(pin_raw)
    install_raw = read_file(ctx.path(INSTALL_WORK) / "receipt.json", modes=(0o600,))
    installed = strict_json(install_raw)
    require(digest(install_raw) == plan["installed_receipt_sha256"] and
            installed["status"] == "C_OFFLINE_CANDIDATE_INSTALLED_NOT_STARTED" and installed["lock_released"] is True and
            installed["runtime_manifest_sha256"] == config["runtime_manifest_sha256"], "C_LIVE_OFFLINE_INSTALL_NOT_ACCEPTED")
    expected = dict(source_commit=installed["source_commit"], runtime_manifest_sha256=config["runtime_manifest_sha256"],
        plan_sha256=digest(plan_raw), controller_sha256=digest(read_file(release / (artifact.PREFIX+"lifecycle.py"), modes=(0o444,),limit=1048576)))
    allowed = approval(pin, expected, ctx.now())
    require(ctx.current_approval(allowed["approval_comment_id"]) == pin["approval_body"], "C_LIVE_APPROVAL_CHANGED")
    installed_acceptance=ctx.verify_installed(installed,config)
    packet = plan["signed_admission"]
    require(type(packet) is dict and set(packet) == {"admission", "signature"}, "C_LIVE_ADMISSION_PACKET")
    authority = DetachedRSA(ctx.path(config["authority_public_key"]), config["authority_public_key_sha256"])
    verify_admission(packet["admission"],packet["signature"],authority,config,plan["acceptance"],ctx.now_ms(),HOST)
    require(packet["admission"]["approval_comment_id"] == allowed["approval_comment_id"] and
            packet["admission"]["expires_at_ms"] + 30000 <= allowed["expires_at"]*1000 and
            plan["acceptance"]["owner_approval_id"] == str(allowed["approval_comment_id"]), "C_LIVE_APPROVAL_WINDOW_BOUND")
    proof_raw = read_file(ctx.path(NETWORK_PROOF), modes=(0o600,), limit=32768)
    require(digest(proof_raw) == plan["network_proof_sha256"], "C_LIVE_ROOT_PROOF_PIN")
    proof = strict_json(proof_raw)
    network_proof(proof,config,ctx.now_ms())
    require(proof["expires_at_ms"] >= packet["admission"]["expires_at_ms"] and
            ctx.table_shape(config["network_policy"]["table"]) == proof["table_shape_sha256"], "C_LIVE_NFT_DRIFT")
    before, shared = frozen_b(ctx), ctx.units(SHARED)
    ctx.verify_manager_profiles();ctx.quiescent(config)
    require(all(row["MainPID"] == "0" and row["ActiveState"] == "inactive" and row["SubState"] == "dead"
                for row in ctx.states().values()), "C_LIVE_CANDIDATE_ALREADY_RUNNING")
    loaded=ctx.units(tuple(UNITS.values()))
    for name,row in loaded.items():
        require(row['LoadState']=='loaded' and row['ActiveState']=='inactive' and not row['DropInPaths'] and
                row['FragmentPath']==str(ctx.path('/etc/systemd/system')/name),'C_LIVE_MANAGER_UNIT_DRIFT')
        enabled=ctx.run(['/usr/bin/systemctl','is-enabled',name])
        require(enabled.returncode in (0,1) and enabled.stdout.strip() in ('static','disabled'),
                'C_LIVE_CANDIDATE_ENABLED')
    ctx.verify_custody_and_snapshot(config,ctx.now_ms(),packet["admission"]["expires_at_ms"])
    objects = ctx.temporary_objects(config)
    require(all(ctx.path(name).lstat().st_dev==ctx.path('/run').stat().st_dev for name in objects),
            'C_LIVE_TEMPORARY_CROSS_FILESYSTEM')
    old_acceptance = read_file(ctx.path(config['acceptance_path']), modes=(0o444,))
    previous = strict_json(old_acceptance)
    require(previous==installed_acceptance and previous['owner_approved'] is False and
            set(previous)==set(plan['acceptance']), 'C_LIVE_ACCEPTANCE_PRESTATE')
    revoked_admission=ctx.path(config['admission_path']).with_name('.live-admission-revoked-'+str(allowed['approval_comment_id'])+'.json')
    for name in (config['admission_path'],WORK,LOCK,QUARANTINE):
        require(not os.path.lexists(ctx.path(name)), 'C_LIVE_PREEXISTING_ATTEMPT_OR_ADMISSION')
        trusted_directory(ctx.path(name).parent)
    require(not os.path.lexists(revoked_admission),'C_LIVE_REVOKED_ADMISSION_EXISTS')
    require(not os.path.lexists(ctx.path(REVOKE)), 'C_LIVE_REVOKED')
    require(read_file(ctx.path(PIN), modes=(0o600,),limit=110000)==pin_raw and
            ctx.current_approval(allowed['approval_comment_id'])==pin['approval_body'] and
            ctx.now()<allowed['expires_at'], 'C_LIVE_AUTHORITY_CHANGED_BEFORE_CLAIM')
    work=ctx.path(WORK);work.mkdir(mode=0o700);os.chmod(work,0o700);fsync_dir(work.parent)
    lock=ctx.path(LOCK); lock_identity=None;start_attempted=False;stop_attempted=False
    receipt=dict(schema_version=1,action=ACTION,approval_comment_id=allowed['approval_comment_id'],
        status='PREPARING',phase='claim',writer_enabled=False,retry_allowed=False,network_changes=False,
        start_attempted=False,stop_attempted=False,temporary_quarantined=False)
    def save():atomic_receipt(work/'receipt.json',receipt)
    def stop_and_quarantine():
        nonlocal stop_attempted
        stop_attempted=True;receipt.update(stop_attempted=True,phase='stop')
        save()
        r=ctx.run(['/usr/bin/systemctl','stop',UNITS['worker.service'],UNITS['broker.service'],UNITS['network-verified.target']])
        require(r.returncode==0,'C_LIVE_STOP_UNKNOWN')
        require(all(row['MainPID']=='0' and row['ActiveState'] in ('inactive','failed') and
                    row['SubState'] in ('dead','failed') for row in ctx.states().values()),'C_LIVE_PROCESSES_REMAIN')
        ctx.quiescent(config)  # UID-wide scan, not just MainPID=0.
        require(ctx.temporary_objects(config)==objects,'C_LIVE_TEMPORARY_IDENTITY_CHANGED')
        quarantine=ctx.path(QUARANTINE);quarantine.mkdir(mode=0o700);os.chmod(quarantine,0o700);fsync_dir(quarantine.parent)
        require(all(ctx.path(name).lstat().st_dev==quarantine.stat().st_dev for name in objects),
                'C_LIVE_TEMPORARY_CROSS_FILESYSTEM')
        for index,name in enumerate(objects):rename_new(ctx.path(name),quarantine/('temporary-%d'%index))
        if os.path.lexists(ctx.path(config['admission_path'])):
            require(read_file(ctx.path(config['admission_path']),modes=(0o444,))==canonical_bytes(packet),
                    'C_LIVE_ADMISSION_DRIFT')
            rename_new(ctx.path(config['admission_path']),revoked_admission)
        receipt.update(temporary_quarantined=True,phase='stopped',dedicated_uids_quiescent=True)
        save()
    try:
        save();lock.mkdir(mode=0o700);os.chmod(lock,0o700);fsync_dir(lock.parent)
        s=lock.lstat();lock_identity=(s.st_dev,s.st_ino)
        write_once(work/'consumed-approval.json',pin_raw)
        write_once(work/'plan.json',plan_raw);write_once(work/'acceptance.before.json',old_acceptance)
        # Store granted acceptance only after exact root and independently signed admission.
        tmp=ctx.path(config['acceptance_path']).with_name('.live-acceptance-new')
        write_once(tmp,canonical_bytes(plan['acceptance']),mode=0o444)
        require(read_file(ctx.path(config['acceptance_path']),modes=(0o444,))==old_acceptance,'C_LIVE_ACCEPTANCE_DRIFT')
        os.replace(tmp,ctx.path(config['acceptance_path']));fsync_dir(tmp.parent)
        write_once(ctx.path(config['admission_path']),canonical_bytes(packet),mode=0o444)
        receipt['phase']='start';save()
        require(ctx.now_ms()<packet['admission']['expires_at_ms'] and
                ctx.table_shape(config['network_policy']['table'])==proof['table_shape_sha256'] and
                not os.path.lexists(ctx.path(REVOKE)), 'C_LIVE_GATE_CHANGED_BEFORE_START')
        start_attempted=True;receipt['start_attempted']=True;start_ms=ctx.now_ms();save()
        require(ctx.run(['/usr/bin/systemctl','start',UNITS['network-verified.target']]).returncode==0,'C_LIVE_TARGET_START_FAILED')
        require(ctx.run(['/usr/bin/systemctl','start','--no-block',UNITS['worker.service']]).returncode==0,'C_LIVE_START_UNKNOWN')
        receipt['phase']='observe';save()
        startup_deadline=ctx.now_ms()+20000;seen_running=False;seen_pids=None
        approval_check_at=ctx.now_ms()+30000
        while True:
            require(not os.path.lexists(ctx.path(REVOKE)), 'C_LIVE_OWNER_REVOKED')
            require(ctx.now_ms()<packet['admission']['expires_at_ms'], 'C_LIVE_WINDOW_EXPIRED')
            require(read_file(ctx.path(PIN),modes=(0o600,),limit=110000)==pin_raw,'C_LIVE_PIN_REVOKED')
            if ctx.now_ms()>=approval_check_at:
                require(ctx.current_approval(allowed['approval_comment_id'])==pin['approval_body'],
                        'C_LIVE_APPROVAL_CHANGED_DURING_WINDOW')
                approval_check_at=ctx.now_ms()+30000
            network_proof(proof,config,ctx.now_ms())
            require(ctx.table_shape(config['network_policy']['table'])==proof['table_shape_sha256'],'C_LIVE_NFT_DRIFT')
            require(frozen_b(ctx)==before and ctx.units(SHARED)==shared,'C_LIVE_PROTECTED_OBJECT_CHANGED')
            rows=ctx.states();worker=rows[UNITS['worker.service']];broker=rows[UNITS['broker.service']]
            require(all(row['ActiveState']!='failed' for row in rows.values()),'C_LIVE_SERVICE_FAILED')
            if worker['ActiveState']=='active' and worker['SubState']=='running':
                seen_running=True
                require(broker['ActiveState']=='active' and broker['SubState']=='running' and
                        int(worker['MainPID'])>0 and int(broker['MainPID'])>0,'C_LIVE_BROKER_NOT_RUNNING')
                pids=(worker['MainPID'],broker['MainPID'])
                require(seen_pids is None or seen_pids==pids,'C_LIVE_SERVICE_RESTARTED')
                seen_pids=pids
            elif seen_running or worker['Result'] not in ('success',''):
                require(worker['MainPID']=='0' and worker['ActiveState']=='inactive' and
                        worker['Result']=='success' and worker['ExecMainStatus']=='0', 'C_LIVE_WORKER_EXIT_FAILED')
                state=ctx.read_window(config,plan['acceptance'])
                tested=_tested_object(config)
                require(state['status']=='PASS_SHADOW_WINDOW' and state['window_id']==plan['acceptance']['window_id'] and
                        state['acceptance_config_sha256']==hash_value(plan['acceptance']) and
                        state['tested_object']==tested and state['tested_object_sha256']==hash_value(tested) and
                        state['writer_enabled'] is False and state['production_authorized'] is False and
                        _finalize(copy.deepcopy(state),plan['acceptance'])['status']=='PASS_SHADOW_WINDOW',
                        'C_LIVE_WINDOW_NOT_PASS')
                require(type(state['started_at_ms']) is int and type(state['deadline_ms']) is int and
                        start_ms<=state['started_at_ms']<=start_ms+20000 and
                        state['deadline_ms']==state['started_at_ms']+plan['acceptance']['duration_seconds']*1000 and
                        ctx.now_ms()>=state['deadline_ms'] and
                        all(sample['cycle_status']=='PASS_READONLY_SHADOW_CYCLE' for sample in state['samples']) and
                        len({sample['snapshot_generation_id'] for sample in state['samples']})==len(state['samples']),
                        'C_LIVE_WINDOW_DURATION_OR_SAMPLE_IDENTITY')
                receipt['window_receipt_sha256']=hash_value(state)
                break
            else:require(ctx.now_ms()<startup_deadline,'C_LIVE_STARTUP_TIMEOUT')
            ctx.sleep(1)
        stop_and_quarantine()
        require(frozen_b(ctx)==before and ctx.units(SHARED)==shared,'C_LIVE_PROTECTED_OBJECT_CHANGED')
        s=lock.lstat()
        require((s.st_dev,s.st_ino)==lock_identity and stat.S_ISDIR(s.st_mode) and s.st_uid==0 and
                stat.S_IMODE(s.st_mode)==0o700 and not list(lock.iterdir()),'C_LIVE_LOCK_CHANGED')
        lock.rmdir();fsync_dir(lock.parent)
        receipt.update(status='PASS_READONLY_WINDOW_STOPPED_AND_QUARANTINED',phase='complete',lock_released=True)
        save();return receipt
    except BaseException as error:
        receipt.update(status='HOLD_PRESERVE_EVIDENCE',error_type=type(error).__name__,
            error=str(error) if type(error).__name__=='GateError' else 'BOUNDED_FAILURE')
        if not stop_attempted:
            try:stop_and_quarantine()
            except BaseException as stop_error:
                receipt.update(stop_error_type=type(stop_error).__name__,stop_result='UNKNOWN_PRESERVE_EVIDENCE')
        receipt['status']='HOLD_PRESERVE_EVIDENCE';receipt['start_attempted']=start_attempted
        save();raise


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);args=p.parse_args(argv)
    os.umask(0o077)
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(RuntimeError('SIGTERM')))
    signal.signal(signal.SIGHUP,lambda *_:(_ for _ in ()).throw(RuntimeError('SIGHUP')))
    try:
        result=supervise(args.plan);print(json.dumps(result,sort_keys=True));return 0
    except BaseException as error:
        print(json.dumps({'status':'HOLD_PRESERVE_EVIDENCE','error_type':type(error).__name__,
                          'retry_allowed':False}),flush=True);return 2


if __name__=='__main__':sys.exit(main())
