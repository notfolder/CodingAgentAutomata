"""
consumer の Zscaler 設定を扱うモジュール。

consumer の環境変数（`.zscaler/zscaler.env` から compose が渡す）から Zscaler 設定を読み、
CLI コンテナへ渡す環境変数と、CLI エージェントへの指示文を作る。
"""

import os
from dataclasses import dataclass
from typing import Mapping, Optional

# CLI コンテナの中の Zscaler の証明書と、OS の証明書の束の場所
_ZSCALER_CERT_PATH = "/usr/local/share/ca-certificates/zscaler.crt"
_CA_BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"

# Zscaler 設定が有効なときに、F-3・F-4 のプロンプトの末尾に足す指示文
_ZSCALER_INSTRUCTION = (
    "## Zscaler 環境での作業について\n\n"
    "この環境は Zscaler の配下にある。外への通信は環境変数のプロキシ"
    "（HTTPS_PROXY・HTTP_PROXY。除外宛先は NO_PROXY）を経由する。\n"
    f"Zscaler の証明書は `{_ZSCALER_CERT_PATH}`、証明書の束は `{_CA_BUNDLE_PATH}` にある。\n"
    "- 開発するシステムの Dockerfile と docker compose の設定には、ビルド時に外から証明書と"
    "プロキシの宛先を渡せる作りを組み込み、証明書ファイルそのものはリポジトリにコミットしない。\n"
    "- 開発するシステムの部品どうしの通信は、除外宛先（NO_PROXY）に入れる。\n"
    "- 証明書の検証を無効にする設定（証明書のエラーを無視する設定を含む）は使わない。\n"
    "- Playwright の Chromium と WebKit は Zscaler の証明書を信頼済み。"
    "Firefox は信頼させられないので使わない。"
)


@dataclass(frozen=True)
class ZscalerSettings:
    """
    consumer の Zscaler 設定（変更不能）。

    Attributes:
        enabled: Zscaler 設定が有効か
        proxy_url: プロキシの宛先（無効なら空）
        no_proxy: 除外宛先（カンマ区切り。無効なら空）
    """

    enabled: bool
    proxy_url: str = ""
    no_proxy: str = ""

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "ZscalerSettings":
        """
        環境変数から Zscaler 設定を読む。

        `ZSCALER_ENABLED` が `true` のときだけ有効とし、プロキシの宛先は `HTTPS_PROXY`、
        除外宛先は `NO_PROXY` から読む。

        Args:
            environ: 環境変数の辞書（省略時は os.environ）

        Returns:
            ZscalerSettings: 読み込んだ設定
        """
        env: Mapping[str, str] = os.environ if environ is None else environ
        enabled: bool = env.get("ZSCALER_ENABLED", "").strip().lower() == "true"
        if not enabled:
            return cls(enabled=False)
        return cls(
            enabled=True,
            proxy_url=env.get("HTTPS_PROXY", "") or env.get("https_proxy", ""),
            no_proxy=env.get("NO_PROXY", "") or env.get("no_proxy", ""),
        )

    def build_cli_env(self) -> dict[str, str]:
        """
        CLI コンテナへ渡す環境変数を返す。

        有効なときはプロキシの宛先と除外宛先（大文字版と小文字版）と `ZSCALER_ENABLED=true`、
        無効なときは `ZSCALER_ENABLED=false` だけを返す。

        Returns:
            dict[str, str]: 環境変数名から値への辞書
        """
        if not self.enabled:
            return {"ZSCALER_ENABLED": "false"}
        return {
            "ZSCALER_ENABLED": "true",
            "HTTP_PROXY": self.proxy_url,
            "HTTPS_PROXY": self.proxy_url,
            "http_proxy": self.proxy_url,
            "https_proxy": self.proxy_url,
            "NO_PROXY": self.no_proxy,
            "no_proxy": self.no_proxy,
        }

    def build_instruction(self) -> str:
        """
        CLI エージェントへの指示文を返す。

        Returns:
            str: 有効なら指示文、無効なら空文字
        """
        return _ZSCALER_INSTRUCTION if self.enabled else ""
