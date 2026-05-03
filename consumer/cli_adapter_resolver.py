"""
CLI アダプタ設定の解決・起動コマンド・環境変数構築モジュール。

cli_adapters テーブルから CLI 設定を取得し、
環境変数辞書と起動コマンド文字列を構築する。
"""

import json
import logging
from typing import Callable, Optional

from sqlalchemy.orm import Session

from shared.models.db import CLIAdapter

# ロガーを設定
logger = logging.getLogger(__name__)


class CLIAdapterResolver:
    """
    CLI アダプタ設定を解決し、環境変数と起動コマンドを構築するクラス。

    cli_adapters テーブルから設定を取得し、
    CLI コンテナ起動に必要な環境変数辞書とコマンド文字列を生成する。
    """

    def __init__(self, db_session_factory: Callable[[], Session]) -> None:
        """
        初期化。

        Args:
            db_session_factory: SQLAlchemy Session を生成するファクトリ関数
        """
        self._db_session_factory: Callable[[], Session] = db_session_factory

    def resolve(self, cli_id: str) -> Optional[CLIAdapter]:
        """
        cli_id に対応する CLI アダプタ設定を DB から取得する。

        Args:
            cli_id: CLI エージェント識別子（例: claude, opencode）

        Returns:
            CLIAdapter | None: 見つかった場合は CLIAdapter オブジェクト、なければ None
        """
        with self._db_session_factory() as session:
            adapter: Optional[CLIAdapter] = (
                session.query(CLIAdapter)
                .filter(CLIAdapter.cli_id == cli_id)
                .first()
            )
            if adapter is None:
                logger.warning("CLIAdapterResolver: cli_id='%s' が見つかりません", cli_id)
                return None
            # セッションを閉じる前にデータをデタッチして返す
            session.expunge(adapter)
            return adapter

    def fetch_all_container_images(self) -> list[str]:
        """
        DB に登録されている全 CLI アダプタの container_image を重複なく返す。

        consumer 起動時のウォームアップ対象イメージ取得に使用する。
        DB 接続エラーが発生した場合は空リストを返す。

        Returns:
            list[str]: container_image 文字列のリスト
        """
        try:
            with self._db_session_factory() as session:
                rows = session.query(CLIAdapter.container_image).all()
                return list({row.container_image for row in rows})
        except Exception as exc:
            logger.warning(
                "CLIAdapterResolver.fetch_all_container_images: 取得失敗（空リストを返します）: %s", exc
            )
            return []

    def build_env_vars(
        self,
        adapter: CLIAdapter,
        info: dict,
    ) -> dict[str, str]:
        """
        CLI アダプタの env_mappings に基づいて環境変数辞書を構築する。

        env_mappings は {"情報キー": "環境変数名"} 形式の辞書。
        情報キー: llm_api_key, llm_base_url, prompt, model, mcp_config

        config_content_env が設定されている場合は、llm_base_url と mcp_config を
        JSON 形式でその環境変数にまとめてセットする（opencode 向け設定）。

        Args:
            adapter: CLI アダプタ設定オブジェクト
            info: 渡す情報辞書
                - llm_api_key: LiteLLM Proxy の Virtual Key
                - llm_base_url: LiteLLM Proxy の ベースURL
                - prompt: CLI に渡すプロンプトテキスト
                - model: 使用する LLM モデル名
                - mcp_config: MCP 設定 JSON 文字列

        Returns:
            dict[str, str]: 環境変数名→値の辞書
        """
        env_vars: dict[str, str] = {}
        env_mappings: dict = adapter.env_mappings or {}

        # config_content_env が設定されている場合は JSON 形式でまとめてセット（opencode 向け）
        if adapter.config_content_env:
            config_content: dict = {}
            # LiteLLM ベースURLを opencode の provider.{provider_id}.options.baseURL 形式で設定
            # opencode の設定スキーマではルートレベルに "baseURL" キーは使えないため、
            # provider セクションにネストして渡す必要がある
            if info.get("llm_base_url"):
                # model 値（例: "openai/gpt-4o"）の "/" 前部分をプロバイダーIDとして使用
                model_str: str = info.get("model", "openai/gpt-4o-mini")
                provider_id: str = (
                    model_str.split("/")[0] if "/" in model_str else "openai"
                )
                config_content["provider"] = {
                    provider_id: {
                        "options": {
                            "baseURL": info["llm_base_url"],
                        }
                    }
                }
            # MCP 設定を opencode の "mcp" キーで設定
            # opencode ではルートレベルに "mcpServers" キーは使えず "mcp" を使う
            if info.get("mcp_config"):
                try:
                    mcp_parsed = json.loads(info["mcp_config"])
                    # _build_mcp_config は {"mcpServers": {...}} 形式で返すため
                    # "mcp" キーに変換して設定する（opencode 仕様）
                    mcp_servers = mcp_parsed.get("mcpServers", {})
                    if mcp_servers:
                        config_content["mcp"] = mcp_servers
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "CLIAdapterResolver: mcp_config の JSON パースに失敗しました"
                    )
            env_vars[adapter.config_content_env] = json.dumps(
                config_content, ensure_ascii=False
            )

        # env_mappings に基づいて環境変数をセット
        for info_key, env_name in env_mappings.items():
            if not env_name:
                # env_name が null/空の場合はスキップ
                continue
            value: Optional[str] = info.get(info_key)
            if value is not None:
                env_vars[env_name] = str(value)

        logger.debug(
            "CLIAdapterResolver.build_env_vars: env_keys=%s",
            list(env_vars.keys()),
        )
        return env_vars

    def build_start_command(
        self,
        adapter: CLIAdapter,
        info: dict,
    ) -> str:
        """
        start_command_template に変数を展開して起動コマンドを構築する。

        {model}, {mcp_config} 変数を展開する。
        プロンプトはファイル経由で渡すため {prompt} 変数は使用しない。

        Args:
            adapter: CLI アダプタ設定オブジェクト
            info: 渡す情報辞書
                - model: 使用する LLM モデル名
                - mcp_config: MCP 設定 JSON 文字列

        Returns:
            str: 変数展開済みの起動コマンド文字列
        """
        import re as _re

        command: str = adapter.start_command_template

        # {model}, {mcp_config} を展開
        model: str = info.get("model", "")
        mcp_config: str = info.get("mcp_config", "")

        # mcp_config が空（"{}" や "" など）の場合は --mcp-config 引数ごと削除する
        # 空の MCP 設定を渡すと Claude CLI が "Invalid MCP configuration" エラーを出力して
        # 処理を完了しなくなるため
        if mcp_config and mcp_config.strip() not in ("{}", "null", ""):
            command = command.replace("{mcp_config}", mcp_config)
        else:
            # --mcp-config '...' 全体を削除（シングルクォート内の値を含む）
            command = _re.sub(r"\s*--mcp-config\s+'[^']*\{mcp_config\}[^']*'", "", command)
            # プレースホルダーが残っている場合は削除
            command = command.replace("{mcp_config}", "")

        command = command.replace("{model}", model)

        logger.debug(
            "CLIAdapterResolver.build_start_command: cli_id=%s", adapter.cli_id
        )
        return command
