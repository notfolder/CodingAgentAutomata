# eBPF × Docker-in-Docker 動作検証結果

## 調査目的

CLIコンテナ（`docker:dind`ベース）内でeBPFを使ったTTY読み取り待機検知が可能かどうかを確認するため、以下の2点を実験で検証した。

1. DinD-in-DinD（ネストDinD）が可能か
2. DinD内でeBPFが動作するか

---

## 実験環境

| 項目 | 値 |
|---|---|
| ホストOS | macOS (arm64) |
| Docker | Docker Desktop 29.4.0 |
| Linuxランタイム | kernel 6.12.76-linuxkit, aarch64 |
| cgroupバージョン | cgroup v2 |
| seccomp | builtin（デフォルトプロファイル） |
| AppArmor | なし |

---

## 実験1：DinD-in-DinD（ネストDinD）

### 構成

```
Host Docker daemon
  └─ ebpf-dind-test (docker:29.4.1-dind, --privileged)  ← DinD Level 1
       └─ inner-dind  (docker:29.4.1-dind, --privileged) ← DinD Level 2
            └─ alpine:3.20 → echo "dind-in-dind-ok"      ← 通常コンテナ
```

### 手順

```
# Level 1 起動
docker run --privileged --name ebpf-dind-test -d -e DOCKER_TLS_CERTDIR= docker:29.4.1-dind

# Level 2 起動（Level 1内部から）
docker exec ebpf-dind-test \
  docker run --privileged --name inner-dind -d -e DOCKER_TLS_CERTDIR= docker:29.4.1-dind

# Level 2内でコンテナ実行
docker exec ebpf-dind-test \
  sh -c 'until docker exec inner-dind docker info >/dev/null 2>&1; do sleep 1; done;
         docker exec inner-dind docker run --rm alpine:3.20 echo dind-in-dind-ok'
```

### 結果

**✅ 動作確認済み**。`dind-in-dind-ok` が正常出力。

- Level 1内: Docker 29.4.1、docker compose v5.1.3 動作確認済み
- Level 2内: alpineコンテナ実行確認済み
- `docker compose` は各レベルで利用可能

---

## 実験2：DinD内でのeBPF動作

### 前提条件チェック（DinD Level 1内部）

| チェック項目 | コマンド | 結果 |
|---|---|---|
| BTFファイル | `ls /sys/kernel/btf/vmlinux` | ✅ 存在 |
| 実効ケーパビリティ | `grep CapEff /proc/self/status` | ✅ `000001ffffffffff`（全CAP含む） |
| bpftool動作 | `apk add bpftool && bpftool prog list` | ✅ BPFプログラム一覧取得成功 |
| perf_event_paranoid | `cat /proc/sys/kernel/perf_event_paranoid` | `2`（制限あり、CAP_BPFで回避可能） |

`CAP_BPF` と `CAP_PERFMON` は `--privileged` により全て付与されている。

### Tracee動作確認（DinD Level 1内のDockerから起動）

DinD Level 1の内部Dockerデーモンに対して以下のコマンドでTraceeを起動：

```
docker exec ebpf-dind-test \
  docker run --name tracee-in-dind -d \
    --pid=host --cgroupns=host --privileged \
    -v /etc/os-release:/etc/os-release-host:ro \
    aquasec/tracee:latest \
    --events sched_process_exec --output json
```

### 結果

**✅ 動作確認済み**。`sched_process_exec` イベントが正常取得。

ログ例（DinD内で `docker ps` を実行した際のイベント）：

```json
{
  "eventName": "sched_process_exec",
  "hostName": "7cbe090b88e8",
  "processName": "docker",
  "args": [
    {"name": "argv", "value": ["docker", "ps"]}
  ]
}
```

---

## 重要な技術的注意事項

### eBPFはホストカーネルに作用する

eBPFプログラムはLinuxカーネルレベルで動作するため、**名前空間に閉じない**。DinD内のTraceeは**ホスト全体のプロセスイベント**を観測する。特定コンテナ内のイベントのみを取得するには、cgroupフィルタリングが必要。

### `--pid=host` の意味

DinD内で `--pid=host` を指定すると、そのDinDが動いているホスト（またはさらに外のDinD）のPID名前空間を共有する。これにより、CLIが実行するプロセスのホストPIDが見える状態になる。

### Docker Desktop（macOS/linuxkit）での注意

- `ebpf-dind-test` コンテナを直接ホストDockerで動かし、その内部でTraceeを `--pid=host` なしで起動した場合、コンテナが即時終了した（linuxkitカーネルのcgroup設定の違いが原因と推測）
- `--pid=host --cgroupns=host` を明示することで正常動作した
- 本番Linuxホスト（Ubuntu/Debian/RHEL等）では `/sys/kernel/btf/vmlinux` が標準で存在し、より安定した動作が期待できる

### seccompとeBPFの関係

- Dockerのデフォルトseccompプロファイルは `bpf` システムコールをブロックする
- `--privileged` フラグを使用するとseccomp制限が全て解除される
- `--privileged` を使わない場合は `--security-opt seccomp=unconfined` または `CAP_BPF` を `--cap-add` で追加する必要がある

---

## 結論と実装方針

### 採用構成

```
consumer (host Docker socket経由)
  └─ CLIコンテナ (docker:dind, --privileged)    ← consumerが起動
       ├─ dockerd（ユーザーのdocker compose等）
       └─ Traceeコンテナ (--pid=host --cgroupns=host --privileged)
            └─ eBPFでCLIプロセスのTTY read待機を検知
```

### 必要なコンテナ起動オプション

CLIコンテナ（consumer側）：
- `--privileged=True`（既存設定で対応済み）

Traceeコンテナ（CLIコンテナ内のDockerで起動）：
- `--pid=host`
- `--cgroupns=host`
- `--privileged`

### 機能可否判定

eBPF検知機能はホストカーネルの能力に依存するため、起動時に以下を確認して機能の有効/無効を判定する：

- `/sys/kernel/btf/vmlinux` の存在
- `CAP_BPF` ケーパビリティの有無（`/proc/self/status` の `CapEff` を確認）

どちらかが満たされない場合は、eBPF検知を無効化してタスクを継続する。

---

## 参考：Traceeイメージ

| 項目 | 値 |
|---|---|
| イメージ | `aquasec/tracee:latest` |
| アーキテクチャ | arm64対応済み |
| 最小カーネルバージョン | 5.4 LTS以上 |
| BTF要件 | `/sys/kernel/btf/vmlinux` が必要 |
| 必要ケーパビリティ | `CAP_BPF` + `CAP_PERFMON`（kernel ≥5.8）または `CAP_SYS_ADMIN` |
