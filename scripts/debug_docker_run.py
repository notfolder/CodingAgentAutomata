#!/usr/bin/env python3
"""
docker run の各フェーズの所要時間を計測する検証用スクリプト。

containers.run(detach=True, remove=True) が長時間ブロックする原因を特定するため、
下記のパターンでそれぞれ elapsed を計測して比較する。

使い方:
    python3 scripts/debug_docker_run.py [--image IMAGE] [--network NETWORK]
"""

import argparse
import subprocess
import sys
import time


def _elapsed(start: float) -> str:
    return f"{time.monotonic() - start:.2f}s"


def test_containers_run(image: str, network: str | None) -> None:
    """containers.run(detach=True, remove=True) の elapsed を計測する。"""
    import docker

    client = docker.from_env(timeout=300)
    name = "debug-docker-run-test"

    # 残骸クリーンアップ
    try:
        client.containers.get(name).remove(force=True)
        print("[cleanup] 既存コンテナを削除しました")
    except docker.errors.NotFound:
        pass

    print(f"\n=== containers.run(detach=True, remove=True) ===")
    print(f"  image   : {image}")
    print(f"  network : {network}")
    print(f"  command : echo hello")

    t0 = time.monotonic()
    try:
        container = client.containers.run(
            image=image,
            name=name,
            command="echo hello",
            privileged=True,
            network=network,
            detach=True,
            remove=True,
        )
        print(f"  [run]   containers.run() returned  elapsed={_elapsed(t0)}")
        print(f"  container_id={container.id[:12]}")
    except Exception as exc:
        print(f"  [ERROR] containers.run() failed elapsed={_elapsed(t0)}: {exc}")


def test_create_start(image: str, network: str | None) -> None:
    """containers.create() + container.start() の elapsed を計測する。"""
    import docker

    client = docker.from_env(timeout=300)
    name = "debug-docker-create-start-test"

    # 残骸クリーンアップ
    try:
        client.containers.get(name).remove(force=True)
        print("[cleanup] 既存コンテナを削除しました")
    except docker.errors.NotFound:
        pass

    print(f"\n=== containers.create() + container.start() ===")
    print(f"  image   : {image}")
    print(f"  network : {network}")
    print(f"  command : echo hello")

    t_create = time.monotonic()
    try:
        container = client.containers.create(
            image=image,
            name=name,
            command="echo hello",
            privileged=True,
            network=network,
        )
        print(f"  [create] elapsed={_elapsed(t_create)}  id={container.id[:12]}")
    except Exception as exc:
        print(f"  [ERROR] containers.create() failed elapsed={_elapsed(t_create)}: {exc}")
        return

    t_start = time.monotonic()
    try:
        container.start()
        print(f"  [start]  elapsed={_elapsed(t_start)}")
    except Exception as exc:
        print(f"  [ERROR] container.start() failed elapsed={_elapsed(t_start)}: {exc}")
        container.remove(force=True)
        return

    # ログを取得して表示
    t_log = time.monotonic()
    try:
        logs = container.logs(stdout=True, stderr=True)
        print(f"  [logs]   {logs.decode('utf-8', errors='replace').strip()!r}  elapsed={_elapsed(t_log)}")
    except Exception as exc:
        print(f"  [logs]   取得失敗: {exc}")

    # コンテナ終了を待つ
    t_wait = time.monotonic()
    try:
        result = container.wait(timeout=30)
        print(f"  [wait]   StatusCode={result.get('StatusCode')}  elapsed={_elapsed(t_wait)}")
    except Exception as exc:
        print(f"  [wait]   失敗: {exc}")

    # クリーンアップ
    try:
        container.remove(force=True)
        print("  [rm]     コンテナ削除済み")
    except Exception:
        pass


def test_docker_cli(image: str, network: str | None) -> None:
    """docker CLI (subprocess) で docker run --rm の elapsed を計測する。"""
    print(f"\n=== docker run --rm (CLI subprocess) ===")
    print(f"  image   : {image}")
    print(f"  network : {network}")
    print(f"  command : echo hello")

    cmd = ["docker", "run", "--rm", "--privileged", "--name", "debug-docker-cli-test"]
    if network:
        cmd += ["--network", network]
    cmd += [image, "echo", "hello"]

    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(f"  [run]    elapsed={_elapsed(t0)}")
        print(f"  stdout={result.stdout.strip()!r}")
        print(f"  returncode={result.returncode}")
        if result.stderr:
            print(f"  stderr={result.stderr.strip()!r}")
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] elapsed={_elapsed(t0)}")
    except Exception as exc:
        print(f"  [ERROR]  elapsed={_elapsed(t0)}: {exc}")


def test_create_with_auto_remove(image: str, network: str | None) -> None:
    """
    containers.create(auto_remove=True) + container.start() で
    auto_remove フラグ単独の影響を計測する。
    """
    import docker

    client = docker.from_env(timeout=300)
    name = "debug-docker-autoremove-test"

    try:
        client.containers.get(name).remove(force=True)
    except docker.errors.NotFound:
        pass

    print(f"\n=== containers.create(auto_remove=True) + container.start() ===")

    t_create = time.monotonic()
    container = client.containers.create(
        image=image,
        name=name,
        command="echo hello",
        privileged=True,
        network=network,
        auto_remove=True,
    )
    print(f"  [create] elapsed={_elapsed(t_create)}  id={container.id[:12]}")

    t_start = time.monotonic()
    container.start()
    print(f"  [start]  elapsed={_elapsed(t_start)}")
    print(f"  total elapsed={_elapsed(t_create)}")


def test_containers_run_sleep(image: str, network: str | None) -> None:
    """
    containers.run(detach=True, remove=True) で長時間コマンド (sleep 300) の elapsed を計測。
    echo hello で起きる auto_remove race condition の影響かを確認する。
    """
    import docker

    client = docker.from_env(timeout=300)
    name = "debug-docker-run-sleep-test"

    try:
        client.containers.get(name).remove(force=True)
    except docker.errors.NotFound:
        pass

    print(f"\n=== containers.run(detach=True, remove=True) with sleep 300 ===")

    t0 = time.monotonic()
    try:
        container = client.containers.run(
            image=image,
            name=name,
            command="sleep 300",
            privileged=True,
            network=network,
            detach=True,
            remove=True,
        )
        print(f"  [run]    elapsed={_elapsed(t0)}  id={container.id[:12]}")
    except Exception as exc:
        print(f"  [ERROR]  elapsed={_elapsed(t0)}: {exc}")
    finally:
        try:
            client.containers.get(name).remove(force=True)
        except Exception:
            pass


def test_run_while_dind_running(image: str, network: str | None) -> None:
    """
    DinD コンテナが sleep で動いている間に別名で containers.run を呼んで elapsed を計測。
    並走する DinD コンテナが原因かどうかを確認する。
    """
    import docker

    client = docker.from_env(timeout=300)
    bg_name = "debug-dind-bg"
    run_name = "debug-dind-concurrent"

    for n in [bg_name, run_name]:
        try:
            client.containers.get(n).remove(force=True)
        except docker.errors.NotFound:
            pass

    print(f"\n=== DinD 並走中に containers.run(detach=True, remove=True) ===")

    # バックグラウンドで DinD コンテナを起動 (sleep 300 → dockerd 稼働中)
    bg = client.containers.create(image=image, name=bg_name, command="sleep 300", privileged=True, network=network)
    bg.start()
    print(f"  [bg] DinD コンテナ起動: {bg.id[:12]}")
    time.sleep(3)  # dockerd 起動待ち

    # 別名コンテナを containers.run で起動
    t0 = time.monotonic()
    try:
        c = client.containers.run(
            image=image,
            name=run_name,
            command="echo hello",
            privileged=True,
            network=network,
            detach=True,
            remove=True,
        )
        print(f"  [containers.run] elapsed={_elapsed(t0)}  id={c.id[:12]}")
    except Exception as exc:
        print(f"  [containers.run] ERROR elapsed={_elapsed(t0)}: {exc}")

    # バックグラウンドコンテナを停止
    try:
        bg.remove(force=True)
    except Exception:
        pass
    try:
        client.containers.get(run_name).remove(force=True)
    except Exception:
        pass


def test_create_start_while_dind_running(image: str, network: str | None) -> None:
    """
    DinD コンテナが sleep で動いている間に create+start で別名コンテナを起動して elapsed を計測。
    auto_remove なしで同じ条件を比較する。
    """
    import docker

    client = docker.from_env(timeout=300)
    bg_name = "debug-dind-bg2"
    run_name = "debug-dind-concurrent2"

    for n in [bg_name, run_name]:
        try:
            client.containers.get(n).remove(force=True)
        except docker.errors.NotFound:
            pass

    print(f"\n=== DinD 並走中に containers.create() + container.start() ===")

    bg = client.containers.create(image=image, name=bg_name, command="sleep 300", privileged=True, network=network)
    bg.start()
    print(f"  [bg] DinD コンテナ起動: {bg.id[:12]}")
    time.sleep(3)

    t_create = time.monotonic()
    try:
        container = client.containers.create(
            image=image, name=run_name, command="echo hello", privileged=True, network=network
        )
        print(f"  [create] elapsed={_elapsed(t_create)}  id={container.id[:12]}")
        t_start = time.monotonic()
        container.start()
        print(f"  [start]  elapsed={_elapsed(t_start)}")
        print(f"  total elapsed={_elapsed(t_create)}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    try:
        bg.remove(force=True)
    except Exception:
        pass
    try:
        client.containers.get(run_name).remove(force=True)
    except Exception:
        pass


def test_run_immediately_after_dind_remove(image: str, network: str | None) -> None:
    """
    DinD コンテナ (睡眠中) を force remove した直後に containers.run を呼んで elapsed を計測。
    remove(force=True) 後にデーモンが後始末中で次の start が詰まるかを確認する。
    """
    import docker

    client = docker.from_env(timeout=300)
    bg_name = "debug-dind-to-remove"
    run_name = "debug-dind-after-remove"

    for n in [bg_name, run_name]:
        try:
            client.containers.get(n).remove(force=True)
        except docker.errors.NotFound:
            pass

    print(f"\n=== DinD force remove 直後に containers.run(detach=True, remove=True) ===")

    # DinD コンテナを起動して dockerd が立ち上がるまで待つ
    bg = client.containers.create(image=image, name=bg_name, command="sleep 300", privileged=True, network=network)
    bg.start()
    print(f"  [bg] DinD コンテナ起動: {bg.id[:12]}  → 5秒待機")
    time.sleep(5)

    # force remove（API は即 return するが daemon はバックグラウンドで後始末）
    t_rm = time.monotonic()
    bg.remove(force=True)
    print(f"  [remove(force=True)] elapsed={_elapsed(t_rm)}")

    # 即座に containers.run を呼ぶ
    t0 = time.monotonic()
    try:
        c = client.containers.run(
            image=image,
            name=run_name,
            command="echo hello",
            privileged=True,
            network=network,
            detach=True,
            remove=True,
        )
        print(f"  [containers.run] elapsed={_elapsed(t0)}  id={c.id[:12]}")
    except Exception as exc:
        print(f"  [containers.run] ERROR elapsed={_elapsed(t0)}: {exc}")

    try:
        client.containers.get(run_name).remove(force=True)
    except Exception:
        pass


def test_remove_running_dind(image: str, network: str | None) -> None:
    """
    DinD コンテナを sleep で起動させ、その後 remove(force=True) にかかる時間を計測。
    前回タスクの残骸削除が詰まっているかを確認する。
    """
    import docker

    client = docker.from_env(timeout=300)
    name = "debug-docker-remove-test"

    # 残骸クリーンアップ
    try:
        client.containers.get(name).remove(force=True)
        print("[cleanup] 既存コンテナを削除しました")
    except docker.errors.NotFound:
        pass

    print(f"\n=== remove(force=True) on running DinD container ===")
    print(f"  image   : {image}")
    print(f"  network : {network}")
    print(f"  command : sleep 300  (DinD が dockerd を起動してから sleep)")

    # DinD + sleep 300 で起動（dockerd が立ち上がる）
    t_start = time.monotonic()
    container = client.containers.create(
        image=image,
        name=name,
        command="sleep 300",
        privileged=True,
        network=network,
    )
    container.start()
    print(f"  [start]  elapsed={_elapsed(t_start)}")

    # 少し待って dockerd が立ち上がるのを確認
    print("  [wait]   5秒待機して dockerd 起動を待つ...")
    time.sleep(5)

    # force remove にかかる時間を計測
    t_remove = time.monotonic()
    container.remove(force=True)
    print(f"  [remove(force=True)] elapsed={_elapsed(t_remove)}")
    print(f"  total elapsed={_elapsed(t_start)}")


def test_run_with_existing_running_container(image: str, network: str | None) -> None:
    """
    DinD コンテナが既に起動している状態で同名コンテナの run_container_once 相当処理の elapsed を計測。
    実タスク処理時の「既存コンテナ削除 → 新コンテナ起動」フローを再現する。
    """
    import docker

    client = docker.from_env(timeout=300)
    name = "debug-docker-existing-test"

    # まず同名の DinD コンテナを sleep で起動しておく
    try:
        client.containers.get(name).remove(force=True)
    except docker.errors.NotFound:
        pass

    print(f"\n=== run_container_once 相当: 既存 DinD 削除 → 新コンテナ起動 ===")
    print(f"  image   : {image}")

    prev = client.containers.create(image=image, name=name, command="sleep 300", privileged=True, network=network)
    prev.start()
    print(f"  [前提] 既存コンテナ起動完了（sleep 300）")
    time.sleep(3)  # dockerd が立ち上がるまで少し待つ

    # run_container_once 相当: 既存削除 → containers.run(detach=True, remove=True)
    t0 = time.monotonic()

    t_remove = time.monotonic()
    try:
        old = client.containers.get(name)
        old.remove(force=True)
        print(f"  [cleanup] remove(force=True) elapsed={_elapsed(t_remove)}")
    except docker.errors.NotFound:
        print(f"  [cleanup] NotFound（スキップ）")

    t_run = time.monotonic()
    try:
        container = client.containers.run(
            image=image,
            name=name,
            command="echo hello",
            privileged=True,
            network=network,
            detach=True,
            remove=True,
        )
        print(f"  [containers.run] elapsed={_elapsed(t_run)}  id={container.id[:12]}")
    except Exception as exc:
        print(f"  [containers.run] ERROR elapsed={_elapsed(t_run)}: {exc}")

    print(f"  total elapsed={_elapsed(t0)}")

    # クリーンアップ
    try:
        client.containers.get(name).remove(force=True)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="docker run 各フェーズの elapsed 計測スクリプト")
    parser.add_argument(
        "--image",
        default="coding-agent-cli-exec-claude:latest",
        help="テスト対象イメージ (デフォルト: coding-agent-cli-exec-claude:latest)",
    )
    parser.add_argument(
        "--network",
        default=None,
        help="接続するネットワーク名 (省略時は自動検出を試みる)",
    )
    parser.add_argument(
        "--auto-network",
        action="store_true",
        help="コンテナ外から実行時はネットワーク名を自動検出しない (デフォルト=False)",
    )
    args = parser.parse_args()

    network = args.network
    if network is None and not args.auto_network:
        # デフォルトの compose ネットワーク名を試みる
        network = "codingagentautomata_codingagent_net"
        print(f"[info] --network 未指定のためデフォルト: {network}")

    image = args.image

    print("=" * 60)
    print("docker run 動作検証スクリプト")
    print("=" * 60)

    # 1. docker CLI での計測
    test_docker_cli(image, network)

    # 2. containers.run(detach=True, remove=True) での計測（echo hello）
    test_containers_run(image, network)

    # 3. containers.create() + container.start() での計測（echo hello）
    test_create_start(image, network)

    # 4. auto_remove=True を明示的に設定した create+start
    test_create_with_auto_remove(image, network)

    # 5. containers.run(detach=True, remove=True) で sleep 300（長時間コマンド）
    test_containers_run_sleep(image, network)

    # 7. DinD force remove 直後に containers.run（★ 本命テスト2）
    test_run_immediately_after_dind_remove(image, network)

    # 8. DinD 並走中に containers.run の elapsed 計測（★ 本命テスト）
    test_run_while_dind_running(image, network)

    # 8. DinD 並走中に create+start の elapsed 計測（比較）
    test_create_start_while_dind_running(image, network)

    # 9. 実行中の DinD コンテナへの remove(force=True) elapsed 計測
    test_remove_running_dind(image, network)

    # 10. 既存 DinD コンテナを削除してから新コンテナを run する elapsed 計測
    test_run_with_existing_running_container(image, network)

    print("\n=== 完了 ===")


if __name__ == "__main__":
    main()
