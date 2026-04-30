#!/usr/bin/env bash

set -euo pipefail

# privileged + DinD コンテナ初回 start() 遅延とウォームアップ効果を、
# 既存アプリコード未変更で検証する独立スクリプト。
#
# 検証方法:
# - Docker ソケットをマウントした一時 Python コンテナで docker SDK を実行
# - create() と start() を分離して時間計測
# - baseline: ウォームアップなしの初回実行
# - warmed: 先に warmup 実行後、actual 実行

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

NETWORK_NAME="verify-dind-warmup-net"
IMAGE_NAME="coding-agent-cli-exec-claude:latest"
RUNNER_IMAGE="python:3.12-alpine"
MEASURE_PY=""

cleanup() {
    if [[ -n "$MEASURE_PY" && -f "$MEASURE_PY" ]]; then
        rm -f "$MEASURE_PY"
    fi
    docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

phase() {
  printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1"
}

prepare_network() {
    docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
    docker network create "$NETWORK_NAME" >/dev/null
}

prepare_measure_script() {
  MEASURE_PY="$(mktemp /tmp/verify_dind_warmup.XXXXXX.py)"
  cat > "$MEASURE_PY" <<'PY'
import json
import os
import time
from datetime import datetime

import docker
import docker.errors

network_name = os.environ["NETWORK_NAME"]
image_name = os.environ["IMAGE_NAME"]
test_label = os.environ["TEST_LABEL"]
do_warmup = os.environ["DO_WARMUP"] == "1"

client = docker.from_env(timeout=10800)


def parse_iso(ts: str) -> datetime | None:
    if not ts or ts.startswith("0001-01-01"):
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    if "." in ts:
        head, tail = ts.split(".", 1)
        if "+" in tail:
            frac, tz = tail.split("+", 1)
            frac = (frac + "000000")[:6]
            ts = f"{head}.{frac}+{tz}"
    return datetime.fromisoformat(ts)


def cleanup_container(name: str) -> None:
    try:
        c = client.containers.get(name)
        c.remove(force=True)
    except docker.errors.NotFound:
        pass


def run_one(name: str) -> dict:
    cleanup_container(name)

    t0 = time.monotonic()
    container = client.containers.create(
        image=image_name,
        name=name,
        command=["echo", name],
        privileged=True,
        network=network_name,
        auto_remove=False,
    )
    create_sec = time.monotonic() - t0

    t1 = time.monotonic()
    container.start()
    start_sec = time.monotonic() - t1

    result = container.wait(timeout=120)
    container.reload()
    started_at = container.attrs.get("State", {}).get("StartedAt", "")
    finished_at = container.attrs.get("State", {}).get("FinishedAt", "")
    started_dt = parse_iso(started_at)
    finished_dt = parse_iso(finished_at)
    lifecycle_sec = (
        (finished_dt - started_dt).total_seconds()
        if started_dt is not None and finished_dt is not None
        else None
    )

    exit_code = result.get("StatusCode", -1)
    container.remove(force=True)

    return {
        "name": name,
        "create_sec": round(create_sec, 3),
        "start_sec": round(start_sec, 3),
        "exit_code": exit_code,
        "lifecycle_sec": round(lifecycle_sec, 3) if lifecycle_sec is not None else None,
        "started_at": started_at,
        "finished_at": finished_at,
    }


payload = {
    "label": test_label,
    "image": image_name,
    "network": network_name,
    "warmup": None,
    "actual": None,
}

if do_warmup:
    payload["warmup"] = run_one(f"verify-warmup-{test_label}")

payload["actual"] = run_one(f"verify-actual-{test_label}")
print(json.dumps(payload, ensure_ascii=False))
PY
}

run_measurement() {
    local label="$1"
    local do_warmup="$2"

  docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$MEASURE_PY:/tmp/measure.py:ro" \
    -e NETWORK_NAME="$NETWORK_NAME" \
    -e IMAGE_NAME="$IMAGE_NAME" \
    -e TEST_LABEL="$label" \
    -e DO_WARMUP="$do_warmup" \
    "$RUNNER_IMAGE" \
    sh -lc 'pip install --no-cache-dir docker >/dev/null 2>&1 && python3 /tmp/measure.py'
}

phase "ベースライン計測（ウォームアップなし）"
prepare_measure_script
prepare_network
BASELINE_JSON="$(run_measurement "baseline" "0")"
echo "$BASELINE_JSON"

phase "ウォームアップ後計測"
prepare_network
WARMED_JSON="$(run_measurement "warmed" "1")"
echo "$WARMED_JSON"

phase "比較サマリー"
python3 - <<PY
import json

baseline = json.loads('''$BASELINE_JSON''')
warmed = json.loads('''$WARMED_JSON''')

b_start = baseline["actual"]["start_sec"]
w_warm = warmed["warmup"]["start_sec"] if warmed.get("warmup") else None
w_start = warmed["actual"]["start_sec"]

print("baseline actual.start_sec:", b_start)
print("warmed warmup.start_sec:", w_warm)
print("warmed actual.start_sec:", w_start)

if b_start > 0 and w_start >= 0:
    ratio = w_start / b_start
    print("warmed_actual / baseline_actual:", round(ratio, 3))

print("\n解釈の目安:")
print("- baseline actual.start_sec が大きく、warmed actual.start_sec が小さい場合、")
print("  初回 start() の初期化遅延が存在し、ウォームアップで緩和できる可能性が高い。")
print("- lifecycle_sec が小さいのに start_sec が大きい場合、")
print("  コンテナ実処理ではなく Docker start API 応答待ちで時間を消費している。")
PY
