#!/bin/bash
set -euo pipefail

target=xuanjun-community-preview
expected_revision=9e3a5cec755aee82c58db57b3feeb2e800d40e43
candidate_image=sha256:52b47908222e2da7b20113ba2a9b5c36d63250050cd52ba17f7e703e556a03af
candidate_revision=f66ae300a1fc66bbde80d0b9bbbd8a3f9738aae9
archive=/var/lib/xuanjun-cloud-connection/registered-update-v1/lifecycle/cache/artifact-eac38c0fac13482c23f38a20f795928a8da9ec1213bcb4bd536688cd2f7775ce
archive_sha256=eac38c0fac13482c23f38a20f795928a8da9ec1213bcb4bd536688cd2f7775ce
health=https://uk.wenwenwenyiyiyi.work/community-preview/community/health
portal=https://uk.wenwenwenyiyiyi.work/community-preview/community/portal
lock=/tmp/xuanjun-community-owner25-f66-install.lock
renamed=0

exec 9>"$lock"
flock -n 9 || { echo COMMUNITY_INSTALL_LOCKED >&2; exit 73; }

current_id=$(docker inspect --format '{{.Id}}' "$target")
current_image=$(docker inspect --format '{{.Image}}' "$target")
current_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$current_image")
rollback=xuanjun-community-preview-before-f66ae300-${current_id:0:12}

test "$current_revision" = "$expected_revision"
test "$(docker inspect --format '{{.State.Running}}' "$target")" = true
test "$(docker inspect --format '{{.Config.User}}' "$target")" = 10001:1008
test -z "$(docker ps -aq --filter name=^/${rollback}$)"
curl -fsS --max-time 15 "$health" | grep -q '"READY"'

if ! docker image inspect "$candidate_image" >/dev/null 2>&1; then
  test "$(sha256sum "$archive" | awk '{print $1}')" = "$archive_sha256"
  gzip -dc "$archive" | docker load >/dev/null
fi
test "$(docker image inspect --format '{{.Id}}' "$candidate_image")" = "$candidate_image"
test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$candidate_image")" = "$candidate_revision"
test "$(docker image inspect --format '{{.Config.User}}' "$candidate_image")" = 10001:1008

rollback_install(){
  rc=$?
  set +e
  if [ "$renamed" = 1 ]; then
    rollback_ok=1
    docker logs --tail 100 "$target" >&2 2>/dev/null
    docker stop -t 15 "$target" >/dev/null 2>&1 || rollback_ok=0
    docker rm "$target" >/dev/null 2>&1 || rollback_ok=0
    docker rename "$rollback" "$target" >/dev/null 2>&1 || rollback_ok=0
    docker start "$target" >/dev/null 2>&1 || rollback_ok=0
    rollback_body=
    for _ in $(seq 1 30); do
      rollback_body=$(curl -fsS --max-time 10 "$health" 2>/dev/null || true)
      printf '%s' "$rollback_body" | grep -q '"status": "READY"' && break
      sleep 1
    done
    test "$(docker inspect --format '{{.Id}}' "$target" 2>/dev/null)" = "$current_id" || rollback_ok=0
    test "$(docker inspect --format '{{.Image}}' "$target" 2>/dev/null)" = "$current_image" || rollback_ok=0
    test "$(docker inspect --format '{{.State.Running}}' "$target" 2>/dev/null)" = true || rollback_ok=0
    printf '%s' "$rollback_body" | grep -q '"status": "READY"' || rollback_ok=0
    if [ "$rollback_ok" = 1 ]; then
      echo COMMUNITY_INSTALL_ROLLED_BACK >&2
    else
      echo COMMUNITY_INSTALL_ROLLBACK_FAILED >&2
    fi
  fi
  exit "$rc"
}
trap rollback_install ERR INT TERM

docker rename "$target" "$rollback"
renamed=1
docker stop -t 20 "$rollback" >/dev/null
docker run -d \
  --name "$target" \
  --network bridge \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 64 \
  --memory 512m \
  --cpus 0.5 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --mount type=bind,src=/var/lib/xuanjun-community-preview/config,dst=/var/lib/xuanjun-community-preview/config,readonly \
  --mount type=bind,src=/var/lib/xuanjun-community-preview/data,dst=/var/lib/xuanjun-community-preview/data \
  --mount type=bind,src=/run/xuanjun-community-preview,dst=/run/xuanjun-community-preview \
  "$candidate_image" \
  --plan /var/lib/xuanjun-community-preview/config/host.json \
  --center-keys /var/lib/xuanjun-community-preview/config/center-keys.json \
  --wechat-secret /var/lib/xuanjun-community-preview/config/wechat.json >/dev/null

for _ in $(seq 1 45); do
  body=$(curl -fsS --max-time 10 "$health" 2>/dev/null || true)
  printf '%s' "$body" | grep -q '"READY"' && \
    printf '%s' "$body" | grep -q "\"runtime_source_sha\": \"$candidate_revision\"" && break
  sleep 1
done
test "$(docker inspect --format '{{.Image}}' "$target")" = "$candidate_image"
test "$(docker inspect --format '{{.State.Running}}' "$target")" = true
test "$(docker inspect --format '{{.Config.User}}' "$target")" = 10001:1008
final_body=$(curl -fsS --max-time 15 "$health")
printf '%s' "$final_body" | grep -q '"status": "READY"'
printf '%s' "$final_body" | grep -q "\"runtime_source_sha\": \"$candidate_revision\""
curl -fsS --max-time 15 "$portal" | grep -q '登录社区分账管理后台'
curl -fsS --max-time 15 "$portal" | grep -q 'admin-logged-out'

trap - ERR INT TERM
echo COMMUNITY_F66AE300_INSTALLED
