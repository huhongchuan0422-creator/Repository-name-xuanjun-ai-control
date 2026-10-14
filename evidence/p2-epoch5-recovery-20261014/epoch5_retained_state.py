"""Concrete read-only retained-state gate for the existing UK epoch5 transaction.

Reuses the previously executed fixed-host collector and publisher verifier. No
credential contents are printed. Caller must run this under the installation
lock and bind the returned evidence to a new independent recovery approval.
"""
import contextlib
import hashlib
import io
import json
import inspect_epoch5 as collector
from verify_retained_publisher import verify_row
from prepare_epoch5_bindings import native_binding_delta

RPM_JOURNAL_SHA='ed0ff06c10174299ce376a13200efddae2b0b1c11416983b065c30ef7bacf6f6'
NATIVE='/etc/xuanjun-development/p2-native-binding.json'


def require(value,label):
    if not value:raise ValueError(label)


def validate_observation(value):
    require(value.get('epoch')==5 and value.get('production_mutations')==0 and
            value.get('install_admission')=='NOT_GRANTED','EPOCH5_OBSERVATION_SCOPE')
    require(value.get('pins')==collector.PINS,'EPOCH5_RECEIPT_BINDINGS')
    rows=value['provision_targets']
    require(len(rows)==24 and len({r['target'] for r in rows})==24 and
            all(r['original_state_matches'] is True for r in rows),'EPOCH5_TARGET_DRIFT')
    rows=value['bootstrap']
    require(len(rows)==7 and len({r['target'] for r in rows})==7 and
            all(r['published_identity_matches'] is True and r['journal_state']=='PUBLISHED'
                and r['temporary']=='ABSENT' for r in rows),'EPOCH5_BOOTSTRAP_DRIFT')
    require(value['rpm_journal_sha256']==RPM_JOURNAL_SHA and value['rpm_journal_state']=='INSTALLED',
            'EPOCH5_RPM_JOURNAL')
    rows=value['rpm_versions']
    require(len(rows)==16 and len({r['name'] for r in rows})==16 and
            all(r['matches_candidate'] is True and r['query_rc']==0 for r in rows),'EPOCH5_RPM_DRIFT')
    rows=value['publisher']
    require(len(rows)==2 and len({r['target'] for r in rows})==2 and
            all(r['root_identity_matches'] is True and r['journal_state']=='PUBLISHED'
                and r['stage_state']=='ABSENT' for r in rows),'EPOCH5_PUBLISHER_DRIFT')
    require(set(value['tls'])=={'config','work','logs'},'EPOCH5_TLS_DIRECTORIES')
    parsed=value['regular_config_parse_only']
    require(parsed['pass'] is True and parsed['acme_called'] is False and len(parsed['modes'])==2 and {r['mode'] for r in parsed['modes']}=={'renew','dry-run'} and all(r['pass'] is True for r in parsed['modes']),'EPOCH5_CERTBOT_PARSE_FAILED')
    return value


def capture_retained(new_manifest_sha):
    # Collector checks root/hostname, exact receipt pins, private file metadata,
    # RPM versions, temporary parse-only config, and pins again after collection.
    output=io.StringIO()
    with contextlib.redirect_stdout(output):collector.main()
    lines=output.getvalue().splitlines()
    require(len(lines)==3 and lines[0].startswith('EPOCH5_PARTIAL_EFFECTS=') and
            lines[1].startswith('EPOCH5_PARTIAL_EFFECTS_SHA256=') and
            lines[2]=='OBSERVATION_ONLY_NOT_RESUME_ADMISSION','EPOCH5_COLLECTOR_OUTPUT')
    packed=lines[0].split('=',1)[1].encode()
    require(hashlib.sha256(packed).hexdigest()==lines[1].split('=',1)[1],'EPOCH5_COLLECTOR_HASH')
    value=validate_observation(json.loads(packed.decode()))
    path=collector.T+'/publisher-bootstrap.json'
    raw,unused=collector.file_data(path)
    require(collector.sha(raw)==collector.PINS[path],'EPOCH5_PUBLISHER_JOURNAL_CHANGED')
    rows=json.loads(raw.decode())['directories']
    require(len(rows)==2 and len({r['target'] for r in rows})==2,'EPOCH5_PUBLISHER_COUNT')
    content=[verify_row(row) for row in rows]
    native,unused=collector.file_data(NATIVE)
    original,unused=collector.file_data(collector.T+'/epoch3-prior-receipts/native-binding-original.json')
    require(native_binding_delta(original,'338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09')==native,'EPOCH5_CURRENT_NATIVE_BINDING')
    next_native=native_binding_delta(original,new_manifest_sha)
    from observe_epoch5 import capture
    current=capture()
    require(all(r['matches_original_absent_or_masked'] is True for r in current['targets']),'EPOCH5_TARGET_EFFECTS')
    value['current_hold_inventory']=current
    import p2_tls_lifecycle as tls
    raw,unused=collector.file_data(collector.T+'/tls-lifecycle.json')
    require(json.loads(raw.decode())['fingerprint']==tls.fingerprint(tls.ROOT),'EPOCH5_TLS_FINGERPRINT')
    # All copied evidence must still refer to the same retained state.
    for path,wanted in collector.PINS.items():
        require(collector.sha(collector.file_data(path)[0])==wanted,'EPOCH5_FINAL_RECEIPT_DRIFT')
    require(collector.file_data(NATIVE)[0]==native,'EPOCH5_NATIVE_BINDING_RACE')
    value['publisher_content_verification']=content
    value['native_binding_transform']={'old_sha256':collector.sha(native),
                                       'new_sha256':collector.sha(next_native),
                                       'new_manifest_sha256':new_manifest_sha}
    evidence=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    return {'evidence':value,'evidence_sha256':collector.sha(evidence),
            'native_binding_before':native,'native_binding_after':next_native}
