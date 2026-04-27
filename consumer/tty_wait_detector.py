"""
Tracee を使用して TTY 待機を検知するモジュール。

DinD（Docker in Docker）構成の Docker クライアントを使用して
Tracee コンテナを起動し、CLI コンテナの TTY 読み取り待機を検知する。
"""

import json
import logging
from typing import Optional

# ロガーを設定
logger = logging.getLogger(__name__)

# Tracee コンテナの起動オプション
_TRACEE_EVENTS = "read"
_TRACEE_OUTPUT_FORMAT = "json"


class TTYWaitDetector:
    """
    Tracee コンテナを起動して CLI コンテナの TTY 待機を検知するクラス。

    DinD 構成のため、CLIコンテナが接続しているDockerソケットを経由して
    Tracee コンテナを起動し、eBPF によって read システムコールを監視する。
    """

    def __init__(
        self,
        dind_docker_client,
        tracee_image: str = "aquasec/tracee:latest",
        timeout_sec: float = 30.0,
    ) -> None:
        """
        TTYWaitDetector を初期化する。

        Args:
            dind_docker_client: CLI コンテナが接続している Docker クライアント（DinD用）
            tracee_image: 使用する Tracee コンテナイメージ名（デフォルト: aquasec/tracee:latest）
            timeout_sec: イベント監視のタイムアウト秒数（デフォルト: 30.0秒）
        """
        # DinD 構成の Docker クライアント（CLIコンテナと同じDockerソケット）
        self._docker_client = dind_docker_client
        self._tracee_image = tracee_image
        self._timeout_sec = timeout_sec
        # 起動中の Tracee コンテナオブジェクト（停止時に使用）
        self._tracee_container = None
        logger.debug(
            "TTYWaitDetector: 初期化完了 image=%s, timeout=%.1f秒",
            tracee_image,
            timeout_sec,
        )

    def start(self, cli_container_id: str) -> bool:
        """
        Tracee コンテナを起動する。

        --pid=host --cgroupns=host --privileged オプションで起動することで、
        ホストの全プロセスの syscall を監視できるようにする。
        CLI コンテナの read イベントを JSON 形式で出力する。

        Args:
            cli_container_id: 監視対象の CLI コンテナ ID（ログ記録用）

        Returns:
            bool: コンテナの起動に成功した場合は True、失敗した場合は False
        """
        logger.info(
            "TTYWaitDetector.start: Tracee コンテナを起動します "
            "cli_container_id=%s, image=%s",
            cli_container_id,
            self._tracee_image,
        )
        try:
            # Tracee を privileged + pid=host + cgroupns=host で起動
            # --events=read で read syscall のみ監視
            # --output=json で JSON 形式で出力
            self._tracee_container = self._docker_client.containers.run(
                image=self._tracee_image,
                command=f"--events={_TRACEE_EVENTS} --output={_TRACEE_OUTPUT_FORMAT}",
                pid_mode="host",
                cgroupns="host",
                privileged=True,
                # /sys/kernel/btf を BTF 情報としてマウント
                volumes={
                    "/sys/kernel/btf": {
                        "bind": "/sys/kernel/btf",
                        "mode": "ro",
                    },
                    "/sys/kernel/debug": {
                        "bind": "/sys/kernel/debug",
                        "mode": "ro",
                    },
                },
                detach=True,
                remove=False,
                name=f"tracee-tty-detector-{cli_container_id[:12]}",
            )
            logger.info(
                "TTYWaitDetector.start: Tracee コンテナ起動成功 "
                "tracee_container_id=%s",
                self._tracee_container.id,
            )
            return True
        except Exception as exc:
            logger.error(
                "TTYWaitDetector.start: Tracee コンテナの起動に失敗しました: %s",
                exc,
            )
            self._tracee_container = None
            return False

    def poll_event(self, max_lines: int = 100) -> Optional[dict]:
        """
        Tracee のログを読み取り、TTY に関連する read イベントを検索する。

        Tracee が JSON 形式で出力するイベントを解析し、
        TTY デバイス（/dev/pts/ または tty）に関連する read イベントが
        検出された場合はそのイベント辞書を返す。

        Args:
            max_lines: 走査するログ行数の上限（デフォルト: 100）

        Returns:
            Optional[dict]: TTY 待機イベントが見つかった場合はイベント辞書、
                          見つからない場合は None
        """
        if self._tracee_container is None:
            logger.warning("TTYWaitDetector.poll_event: Tracee コンテナが起動していません")
            return None

        try:
            # コンテナのログを取得（最新のmax_linesバイト分）
            logs_bytes: bytes = self._tracee_container.logs(
                stdout=True,
                stderr=False,
                tail=max_lines,
            )
            log_text: str = logs_bytes.decode("utf-8", errors="replace")

            # 各行を JSON としてパースしてイベントを確認する
            for line in log_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event: dict = json.loads(line)
                    # TTY 待機イベントかどうか確認する
                    if self.is_tty_wait(event):
                        logger.info(
                            "TTYWaitDetector.poll_event: TTY 待機イベントを検知しました: %s",
                            event,
                        )
                        return event
                except json.JSONDecodeError:
                    # JSON でない行（起動メッセージ等）はスキップ
                    logger.debug(
                        "TTYWaitDetector.poll_event: JSON パース失敗（スキップ）: %s",
                        line[:100],
                    )
                    continue
        except Exception as exc:
            logger.warning(
                "TTYWaitDetector.poll_event: ログ取得中にエラーが発生しました: %s",
                exc,
            )

        return None

    def stop(self) -> None:
        """
        Tracee コンテナを停止・削除する。

        コンテナが存在しない場合やエラーが発生した場合は無視する（ベストエフォート）。
        """
        if self._tracee_container is None:
            logger.debug("TTYWaitDetector.stop: Tracee コンテナが存在しません（スキップ）")
            return

        container_id = self._tracee_container.id
        logger.info(
            "TTYWaitDetector.stop: Tracee コンテナを停止します container_id=%s",
            container_id,
        )
        try:
            # コンテナを即時停止（タイムアウト0秒）
            self._tracee_container.stop(timeout=0)
            # コンテナを削除
            self._tracee_container.remove(force=True)
            logger.info(
                "TTYWaitDetector.stop: Tracee コンテナを停止・削除しました container_id=%s",
                container_id,
            )
        except Exception as exc:
            logger.warning(
                "TTYWaitDetector.stop: Tracee コンテナの停止・削除に失敗しました（無視）: %s",
                exc,
            )
        finally:
            self._tracee_container = None

    def is_tty_wait(self, event: dict) -> bool:
        """
        イベントが TTY への read 待機かどうかを判定する。

        Tracee の JSON イベントで eventName が "read" であり、
        かつ引数の pathname または fd が TTY デバイスに関連する場合に True を返す。

        Args:
            event: Tracee が出力した JSON イベント辞書

        Returns:
            bool: TTY read 待機イベントの場合は True、そうでない場合は False
        """
        # イベント名が "read" であることを確認する
        event_name: str = event.get("eventName", "")
        if event_name != "read":
            return False

        # 引数からパス名またはファイルディスクリプタ情報を取得する
        args: list = event.get("args", [])
        for arg in args:
            arg_name: str = arg.get("name", "")
            arg_value = arg.get("value", "")

            # pathname 引数が TTY パスを含む場合
            if arg_name == "pathname" and isinstance(arg_value, str):
                if "/dev/pts/" in arg_value or "tty" in arg_value.lower():
                    logger.debug(
                        "TTYWaitDetector.is_tty_wait: TTY pathname を検知 pathname=%s",
                        arg_value,
                    )
                    return True

            # fd 引数が TTY に関連する場合（文字列表現に tty が含まれる）
            if arg_name == "fd" and isinstance(arg_value, str):
                if "/dev/pts/" in arg_value or "tty" in arg_value.lower():
                    logger.debug(
                        "TTYWaitDetector.is_tty_wait: TTY fd を検知 fd=%s",
                        arg_value,
                    )
                    return True

        return False
