"""
CLI コンテナの起動・監視・破棄を管理するモジュール。

Docker SDK を使用して cli-exec コンテナのライフサイクルを管理する。
DinD（Docker in Docker）構成のため privileged=True で起動する。
"""

import io
import logging
import os
import socket
import tarfile
from typing import Optional

import docker
import docker.errors
import docker.models.containers

# ロガーを設定
logger = logging.getLogger(__name__)

DOCKER_CLIENT_TIMEOUT_SEC = int(os.environ.get("DOCKER_CLIENT_TIMEOUT_SEC", "120"))


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
        # 初回起動の重いコンテナでも start() がタイムアウトしにくいよう待機時間を延長
        self._client: docker.DockerClient = docker.from_env(
            timeout=DOCKER_CLIENT_TIMEOUT_SEC
        )
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
        privileged=True（DinD 構成）で起動する。
        command が None の場合はコンテナを常時起動状態に保つ。

        起動失敗（ReadTimeout など）時も作成済みコンテナを必ず削除する。
        事前に同名コンテナが残存していれば起動前に削除する。

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

        # 起動前に同名の残存コンテナを削除（前回失敗の残骸を確実にクリーンアップ）
        try:
            old_container = self._client.containers.get(container_name)
            old_container.remove(force=True)
            logger.info(
                "CLIContainerManager.start_container: 既存コンテナを削除しました name=%s",
                container_name,
            )
        except docker.errors.NotFound:
            pass  # 残存コンテナなし（正常）
        except Exception as exc:
            logger.warning(
                "CLIContainerManager.start_container: 既存コンテナ削除失敗（無視） name=%s: %s",
                container_name,
                exc,
            )

        # コンテナを作成（この時点でコンテナIDを確保する）
        # create() + start() に分離することで、start() が ReadTimeout 等で失敗しても
        # container オブジェクトを保持し、確実に削除できるようにする
        container: docker.models.containers.Container = self._client.containers.create(
            image=image,
            name=container_name,
            environment=env_vars,
            command=command,
            # DinD 構成のため privileged モードで起動
            privileged=True,
            # Consumer コンテナと同一ネットワークに接続（mock_llm/litellm へのサービス名解決のため）
            network=self._cli_network if self._cli_network else None,
        )
        logger.debug(
            "CLIContainerManager.start_container: コンテナ作成完了 container_id=%s",
            container.id,
        )

        # コンテナを起動（失敗時は作成済みコンテナを削除してから再送出）
        try:
            container.start()
        except Exception as exc:
            logger.error(
                "CLIContainerManager.start_container: コンテナ起動失敗 container_id=%s: %s",
                container.id,
                exc,
            )
            try:
                container.remove(force=True)
                logger.info(
                    "CLIContainerManager.start_container: 起動失敗コンテナを削除しました container_id=%s",
                    container.id,
                )
            except Exception as remove_exc:
                logger.warning(
                    "CLIContainerManager.start_container: 起動失敗コンテナ削除失敗（無視）: %s",
                    remove_exc,
                )
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

    def write_file(self, container_id: str, file_path: str, content: str) -> None:
        """
        コンテナ内にファイルを書き込む。

        Docker SDK の put_archive を使用してファイル内容をコンテナに転送する。
        コンテナ起動直後にプロンプトファイルを書き込むために使用する。

        Args:
            container_id: 対象コンテナの ID
            file_path: コンテナ内のファイルパス（例: /tmp/prompt.txt）
            content: 書き込むファイルの内容

        Raises:
            docker.errors.DockerException: ファイル書き込み失敗時
        """
        logger.debug(
            "CLIContainerManager.write_file: container_id=%s, path=%s, size=%d",
            container_id,
            file_path,
            len(content),
        )
        container: docker.models.containers.Container = self._client.containers.get(
            container_id
        )
        content_bytes: bytes = content.encode("utf-8")
        file_name: str = os.path.basename(file_path)
        dir_path: str = os.path.dirname(file_path)

        # tar アーカイブをメモリ上に構築
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            tarinfo = tarfile.TarInfo(name=file_name)
            tarinfo.size = len(content_bytes)
            # 全ユーザーに読み取り権限を付与（644）
            tarinfo.mode = 0o644
            tar.addfile(tarinfo, io.BytesIO(content_bytes))
        tar_buffer.seek(0)

        # 指定ディレクトリにファイルを配置
        container.put_archive(dir_path, tar_buffer.getvalue())
        logger.debug(
            "CLIContainerManager.write_file: ファイルを書き込みました path=%s, size=%d",
            file_path,
            len(content_bytes),
        )

    def configure_git(self, container_id: str, bot_name: str) -> bool:
        """
        コンテナ内で git のグローバル設定を行う。

        git commit 時に user.name と user.email が必要なため、
        コンテナ起動直後に自動設定する。
        設定失敗時はエラーをログに記録するが処理は継続する（True を返す）。

        Args:
            container_id: 対象コンテナの ID
            bot_name: git config に設定するボット名

        Returns:
            bool: 設定処理を試みた場合は True（失敗してもTrueを返す）
        """
        logger.info(
            "CLIContainerManager.configure_git: container_id=%s, bot_name=%s",
            container_id,
            bot_name,
        )
        try:
            # user.name を設定
            name_exit, name_out = self.exec_command(
                container_id,
                f'git config --global user.name "{bot_name}"',
            )
            if name_exit != 0:
                logger.warning(
                    "CLIContainerManager.configure_git: user.name 設定失敗 "
                    "exit=%d, output=%s（処理継続）",
                    name_exit,
                    name_out,
                )

            # user.email を設定
            email_exit, email_out = self.exec_command(
                container_id,
                f'git config --global user.email "{bot_name}@localhost"',
            )
            if email_exit != 0:
                logger.warning(
                    "CLIContainerManager.configure_git: user.email 設定失敗 "
                    "exit=%d, output=%s（処理継続）",
                    email_exit,
                    email_out,
                )

            logger.debug(
                "CLIContainerManager.configure_git: git config 設定完了 container_id=%s",
                container_id,
            )
        except Exception as exc:
            # エラーが発生しても処理は継続する
            logger.error(
                "CLIContainerManager.configure_git: git config 設定中にエラーが発生しました（処理継続）: %s",
                exc,
            )
        return True

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
