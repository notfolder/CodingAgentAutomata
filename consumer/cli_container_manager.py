"""
CLI コンテナの起動・監視・破棄を管理するモジュール。

Docker SDK を使用して cli-exec コンテナのライフサイクルを管理する。
DinD（Docker in Docker）構成のため privileged=True で起動する。
"""

import logging
import os
import socket
from typing import Optional

import docker
import docker.errors
import docker.models.containers

# ロガーを設定
logger = logging.getLogger(__name__)


class CLIContainerManager:
    """
    Docker SDK を使って cli-exec コンテナを管理するクラス。

    コンテナの起動・コマンド実行・ログ取得・停止・プロセス管理を提供する。
    privileged=True（DinD構成）でコンテナを起動する。
    """

    def __init__(self) -> None:
        """
        初期化。

        docker.from_env() で Docker クライアントを初期化する。
        Docker daemon に接続できない場合は例外を送出する。
        """
        # docker.sock 経由で Docker デーモンに接続
        self._client: docker.DockerClient = docker.from_env()
        logger.debug("CLIContainerManager: Docker クライアントを初期化しました")

        # Consumer コンテナ自身が接続しているネットワークを取得（CLI コンテナも同一ネットワークで起動するため）
        self._cli_network: Optional[str] = self._get_self_network()
        logger.info(
            "CLIContainerManager: CLI コンテナ接続先ネットワーク=%s", self._cli_network
        )

    def _get_self_network(self) -> Optional[str]:
        """
        Consumer コンテナ自身が参加している Docker ネットワーク名を返す。

        /proc/self/cgroup または環境変数 CLI_DOCKER_NETWORK から取得する。
        環境変数 CLI_DOCKER_NETWORK が設定されている場合はその値を使用する。

        Returns:
            Optional[str]: ネットワーク名（取得できない場合は None）
        """
        # 環境変数による明示指定を優先
        env_network = os.environ.get("CLI_DOCKER_NETWORK")
        if env_network:
            return env_network

        # Consumer 自身のホスト名（= コンテナ ID の先頭12文字）からネットワークを取得
        try:
            hostname = socket.gethostname()
            self_container = self._client.containers.get(hostname)
            networks = list(
                self_container.attrs.get("NetworkSettings", {})
                .get("Networks", {})
                .keys()
            )
            if networks:
                return networks[0]
        except Exception as exc:
            logger.warning(
                "CLIContainerManager: 自身のネットワーク取得に失敗しました: %s", exc
            )
        return None

    def start_container(
        self,
        container_name: str,
        image: str,
        env_vars: dict[str, str],
        command: Optional[str] = None,
    ) -> str:
        """
        cli-exec コンテナを起動してコンテナ ID を返す。

        コンテナ名は cli-exec-{cli_id}-{task_uuid} 形式を想定。
        privileged=True（DinD 構成）、detach=True で起動する。
        command が None の場合はコンテナを常時起動状態に保つ。

        Args:
            container_name: コンテナ名（cli-exec-{cli_id}-{task_uuid} 形式）
            image: コンテナイメージ名・タグ
            env_vars: コンテナに渡す環境変数辞書
            command: コンテナ起動コマンド（None の場合はイメージデフォルト使用）

        Returns:
            str: 起動したコンテナの ID

        Raises:
            docker.errors.DockerException: コンテナ起動失敗時
        """
        logger.info(
            "CLIContainerManager.start_container: name=%s, image=%s",
            container_name,
            image,
        )
        try:
            container: docker.models.containers.Container = self._client.containers.run(
                image=image,
                name=container_name,
                environment=env_vars,
                command=command,
                # DinD 構成のため privileged モードで起動
                privileged=True,
                # バックグラウンドで起動
                detach=True,
                # コンテナ終了後も自動削除しない（ログ取得のため残す）
                remove=False,
                # Consumer コンテナと同一ネットワークに接続（mock_llm/litellm へのサービス名解決のため）
                network=self._cli_network if self._cli_network else None,
            )
        except docker.errors.APIError as exc:
            # 同名コンテナが残存している場合（409 Conflict）は削除してリトライ
            if exc.status_code == 409:
                logger.warning(
                    "CLIContainerManager.start_container: 同名コンテナ競合（409）のため既存コンテナを削除してリトライ name=%s",
                    container_name,
                )
                try:
                    old_container = self._client.containers.get(container_name)
                    old_container.remove(force=True)
                    logger.info(
                        "CLIContainerManager.start_container: 既存コンテナを削除しました name=%s",
                        container_name,
                    )
                except Exception as remove_exc:
                    logger.warning(
                        "CLIContainerManager.start_container: 既存コンテナ削除失敗 name=%s: %s",
                        container_name,
                        remove_exc,
                    )
                container = self._client.containers.run(
                    image=image,
                    name=container_name,
                    environment=env_vars,
                    command=command,
                    privileged=True,
                    detach=True,
                    remove=False,
                    network=self._cli_network if self._cli_network else None,
                )
            else:
                raise
        logger.info(
            "CLIContainerManager.start_container: container_id=%s", container.id
        )
        return container.id

    def exec_command(
        self,
        container_id: str,
        command: str,
    ) -> tuple[int, str]:
        """
        コンテナ内でコマンドを実行して (exit_code, output) を返す。

        Args:
            container_id: 対象コンテナの ID
            command: 実行するコマンド文字列

        Returns:
            tuple[int, str]: (終了コード, 標準出力テキスト)

        Raises:
            docker.errors.DockerException: コマンド実行失敗時
        """
        logger.debug(
            "CLIContainerManager.exec_command: container_id=%s, command=%s",
            container_id,
            command,
        )
        container: docker.models.containers.Container = self._client.containers.get(
            container_id
        )
        # /bin/sh -c 経由でシェルコマンドとして実行
        result = container.exec_run(
            cmd=["/bin/sh", "-c", command],
            stdout=True,
            stderr=True,
            stream=False,
        )
        exit_code: int = result.exit_code if result.exit_code is not None else -1
        output: str = (
            result.output.decode("utf-8", errors="replace") if result.output else ""
        )
        logger.debug(
            "CLIContainerManager.exec_command: exit_code=%d, output_len=%d",
            exit_code,
            len(output),
        )
        return exit_code, output

    def stop_container(self, container_id: str) -> None:
        """
        コンテナを停止・破棄する。

        エラーが発生しても無視する（すでに停止済みの場合など）。

        Args:
            container_id: 停止するコンテナの ID
        """
        logger.info(
            "CLIContainerManager.stop_container: container_id=%s", container_id
        )
        try:
            container: docker.models.containers.Container = (
                self._client.containers.get(container_id)
            )
            # コンテナを強制停止（タイムアウト0秒）
            container.stop(timeout=0)
            # コンテナを削除
            container.remove(force=True)
        except docker.errors.NotFound:
            logger.debug(
                "CLIContainerManager.stop_container: コンテナが見つかりません（すでに削除済み） container_id=%s",
                container_id,
            )
        except Exception as exc:
            # 停止・削除エラーは無視（ベストエフォート）
            logger.warning(
                "CLIContainerManager.stop_container: エラー（無視）: %s", exc
            )

    def get_stdout_stream(
        self,
        container_id: str,
    ):
        """
        コンテナの標準出力ストリームを取得して返す。

        Docker SDK の logs(stream=True) を使用して非同期ストリームを返す。

        Args:
            container_id: 対象コンテナの ID

        Returns:
            ストリームジェネレータ（各要素はバイト列）
        """
        container: docker.models.containers.Container = self._client.containers.get(
            container_id
        )
        # follow=True でコンテナ実行中もストリームし続ける
        return container.logs(stream=True, follow=True, stdout=True, stderr=True)

    def kill_process(self, container_id: str, pid: int) -> None:
        """
        コンテナ内の指定 PID のプロセスを KILL する。

        Args:
            container_id: 対象コンテナの ID
            pid: KILL するプロセスの PID
        """
        logger.info(
            "CLIContainerManager.kill_process: container_id=%s, pid=%d",
            container_id,
            pid,
        )
        try:
            self.exec_command(container_id, f"kill -9 {pid}")
        except Exception as exc:
            logger.warning(
                "CLIContainerManager.kill_process: KILL失敗（無視）: %s", exc
            )

    def get_container_pid(
        self,
        container_id: str,
        process_name: str,
    ) -> Optional[int]:
        """
        コンテナ内で指定名称のプロセスの PID を取得する。

        pgrep コマンドを使用してプロセス名でPIDを検索する。

        Args:
            container_id: 対象コンテナの ID
            process_name: 検索するプロセス名

        Returns:
            int | None: 見つかった場合はPID、見つからない場合は None
        """
        try:
            exit_code, output = self.exec_command(
                container_id, f"pgrep -x '{process_name}'"
            )
            if exit_code == 0 and output.strip():
                # 複数ある場合は最初の PID を返す
                first_line: str = output.strip().splitlines()[0]
                return int(first_line)
        except (ValueError, Exception) as exc:
            logger.warning(
                "CLIContainerManager.get_container_pid: 取得失敗: %s", exc
            )
        return None
