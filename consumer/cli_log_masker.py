"""
CLI ログの GitLab PAT マスクサービスモジュール。

git clone URL などに含まれる GitLab Personal Access Token を
**** に置換してログを安全に保存できるようにする。
"""

import re


class CLILogMasker:
    """
    CLI ログの GitLab PAT（Personal Access Token）パターンをマスクするクラス。

    以下のパターンを検出して **** に置換する:
    - https://oauth2:TOKEN@host/path  （OAuth2トークン形式）
    - https://TOKEN@host/path         （シンプルトークン形式）
    """

    # oauth2:TOKEN@host パターン（TOKEN 部分を **** に置換）
    _OAUTH2_PATTERN: re.Pattern = re.compile(
        r"(https?://oauth2:)([^@\s]+)(@)",
        re.IGNORECASE,
    )

    # TOKEN@host パターン（TOKEN 部分を **** に置換）
    # oauth2 パターンと区別するため負の後読みを使用
    _TOKEN_AT_PATTERN: re.Pattern = re.compile(
        r"(https?://)(?!oauth2:)([^@\s/]+)(@)",
        re.IGNORECASE,
    )

    def mask(self, log_text: str) -> str:
        """
        PAT パターンを **** でマスクした文字列を返す。

        Args:
            log_text: マスク対象のログテキスト

        Returns:
            str: PAT をマスクしたログテキスト
        """
        # まず oauth2:TOKEN@host パターンをマスク
        masked: str = self._OAUTH2_PATTERN.sub(r"\1****\3", log_text)
        # 次に TOKEN@host パターンをマスク
        masked = self._TOKEN_AT_PATTERN.sub(r"\1****\3", masked)
        return masked
