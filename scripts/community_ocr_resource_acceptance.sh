#!/usr/bin/env bash
# Insert in the existing image job after release build, before image save.
# Does not introduce a concurrent workflow/job or alter source/production.
set -euo pipefail
image="community-preview:${COMMUNITY_IMAGE_SOURCE_SHA:?}"
tests_dir="$(realpath community-image-context/tests)"
evidence="$(pwd)/community-ocr-resource-evidence"
mkdir -p "$evidence"
failed=0
cid=''
case=''
cleanup_container() {
  status=$?
  trap - EXIT
  if [[ -n "$cid" ]]; then
    # Capture independently: one failed Docker query must not skip the rest.
    docker logs "$cid" > "$evidence/$case.interrupted.log" 2>&1 || true
    docker inspect "$cid" > "$evidence/$case.interrupted.inspect.json" 2>&1 || true
    docker rm -f "$cid" > "$evidence/$case.cleanup.txt" 2>&1 || true
  fi
  exit "$status"
}
trap cleanup_container EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
for case in clear maximum_20mp; do
  cid=$(docker create --network=none --read-only --cap-drop=ALL \
    --security-opt=no-new-privileges --pids-limit=64 --memory=4g --memory-swap=4g --cpus=0.5 \
    --user=10001:1008 --env HOME=/home/community --env PYTHONPATH=/app:/app/tests \
    --tmpfs /home/community:rw,nosuid,nodev,size=128m,uid=10001,gid=1008,mode=0700 \
    --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 \
    --mount "type=bind,src=$tests_dir,dst=/app/tests,readonly" \
    --entrypoint python "$image" -B /app/tests/community_ocr_full_host_resources.py --case "$case")
  docker inspect "$cid" > "$evidence/$case.created.json"
  docker start "$cid" > /dev/null
  # Only a CI watchdog, not a changed application timeout or retry condition.
  if ! timeout 240s docker wait "$cid" > "$evidence/$case.exitcode.txt"; then
    printf 'true\n' > "$evidence/$case.watchdog_expired.txt"
    docker kill "$cid" > /dev/null || true
    docker wait "$cid" >> "$evidence/$case.exitcode.txt" || true
  fi
  docker logs "$cid" > "$evidence/$case.log" 2>&1
  docker inspect "$cid" > "$evidence/$case.finished.json"
  if ! python - "$evidence" "$case" "$COMMUNITY_IMAGE_SOURCE_SHA" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);case=sys.argv[2]
report={'case':case,'accepted':False,'final_checkpoint_receipt_complete':False,
        'kernel_memory_peak_bytes':None,
        'peak_sampling_scope':'kernel cgroup high-water mark at completed-test checkpoint before process exit',
        'failure_stage':'parse_container_inspection'}
try:
    inspection=json.loads((root/(case+'.finished.json')).read_text())[0]
    config=inspection['HostConfig'];state=inspection['State']
    report.update(container_id=inspection['Id'],image_id=inspection['Image'],
        exit_code=state['ExitCode'],oom_killed=state['OOMKilled'],
        watchdog_expired=(root/(case+'.watchdog_expired.txt')).exists(),
        requested_limits={k:config.get(k) for k in ('Memory','MemorySwap','NanoCpus','PidsLimit','ReadonlyRootfs','NetworkMode','SecurityOpt','CapDrop')})
    report['failure_stage']='parse_final_checkpoint'
    lines=(root/(case+'.log')).read_text().splitlines()
    receipts=[json.loads(line[len('RESOURCE_RESULT '):]) for line in lines if line.startswith('RESOURCE_RESULT ')]
    report['final_checkpoint_receipt_complete']=len(receipts)==1
    if len(receipts)==1:
        report['kernel_memory_peak_bytes']=int(receipts[0]['final_cgroup']['memory.peak'])
    report['failure_stage']='verify_acceptance'
    assert inspection['Config']['Labels']['org.opencontainers.image.revision']==sys.argv[3]
    assert config['Memory']==config['MemorySwap']==4294967296
    assert config['NanoCpus']==500000000 and config['PidsLimit']==64
    assert config['ReadonlyRootfs'] and config['NetworkMode']=='none'
    assert inspection['Config']['User']=='10001:1008'
    assert any(v in ('no-new-privileges','no-new-privileges=true') for v in config['SecurityOpt'])
    assert 'ALL' in config['CapDrop']
    assert state['ExitCode']==0 and not state['OOMKilled'] and not report['watchdog_expired']
    assert len(receipts)==1 and receipts[0]['accepted'] and receipts[0]['production_limits_enforced']
    assert receipts[0]['case']==case and receipts[0]['functional_checks_passed']
    assert receipts[0]['final_cgroup']['memory.max']=='4294967296'
    assert receipts[0]['final_cgroup']['memory.swap.max']=='0'
    assert report['kernel_memory_peak_bytes']>0
    report['accepted']=True
    report['failure_stage']=None
except Exception as error:
    report['error_type']=type(error).__name__
    raise
finally:
    (root/(case+'.acceptance.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
PY
  then failed=1; fi
  docker rm "$cid" > /dev/null
  cid=''
 done
# Upload community-ocr-resource-evidence/ with if:always in the existing artifact
# step. Missing receipt / OOM / timeout fails acceptance, not a skipped pass.
exit "$failed"
