"""
F-3/F-4 プロンプトテンプレートの変数展開モジュール。

system_settings テーブルから F-3/F-4 プロンプトテンプレートを取得し、
変数を展開して CLI への指示文を生成する。
"""

import logging
from typing import Callable, Optional

from sqlalchemy.orm import Session

from shared.models.db import SystemSetting

# ロガーを設定
logger = logging.getLogger(__name__)

# system_settings テーブルのキー定数
_KEY_F3_TEMPLATE = "f3_prompt_template"
_KEY_F4_TEMPLATE = "f4_prompt_template"


class PromptBuilder:
    """
    プロンプトテンプレートに変数を展開して CLI への指示文を生成するクラス。

    F-3（Issue→MR変換）と F-4（MR処理）それぞれのテンプレートに対応する。
    テンプレートは system_settings テーブルから取得する。
    """

    def __init__(self, db_session_factory: Callable[[], Session]) -> None:
        """
        初期化。

        Args:
            db_session_factory: SQLAlchemy Session を生成するファクトリ関数
        """
        self._db_session_factory: Callable[[], Session] = db_session_factory

    def _get_system_setting(self, key: str) -> Optional[str]:
        """
        system_settings テーブルから設定値を取得する。

        Args:
            key: 設定キー

        Returns:
            str | None: 設定値、存在しない場合は None
        """
        with self._db_session_factory() as session:
            setting: Optional[SystemSetting] = (
                session.query(SystemSetting)
                .filter(SystemSetting.key == key)
                .first()
            )
            if setting is None:
                logger.warning("PromptBuilder: key='%s' が system_settings に見つかりません", key)
                return None
            return setting.value

    def build_f3_prompt(
        self,
        issue_title: str,
        issue_description: str,
        issue_comments: str,
        project_name: str,
        repository_url: str,
    ) -> str:
        """
        F-3（Issue→MR変換）用のプロンプトをテンプレートから生成する。

        DB の f3_prompt_template を取得して変数を展開する。
        変数: {issue_title}, {issue_description}, {issue_comments},
               {project_name}, {repository_url}

        Args:
            issue_title: Issue のタイトル
            issue_description: Issue の説明文
            issue_comments: Issue のコメント一覧（結合済みテキスト）
            project_name: GitLab プロジェクト名
            repository_url: リポジトリ URL

        Returns:
            str: 変数展開済みのプロンプト文字列

        Raises:
            ValueError: テンプレートが存在しない場合
        """
        template: Optional[str] = self._get_system_setting(_KEY_F3_TEMPLATE)
        if not template:
            raise ValueError(
                "F-3 プロンプトテンプレートが system_settings に設定されていません。"
            )

        # テンプレート変数を展開
        prompt: str = template
        prompt = prompt.replace("{issue_title}", issue_title)
        prompt = prompt.replace("{issue_description}", issue_description)
        prompt = prompt.replace("{issue_comments}", issue_comments)
        prompt = prompt.replace("{project_name}", project_name)
        prompt = prompt.replace("{repository_url}", repository_url)

        logger.debug("PromptBuilder.build_f3_prompt: issue_title='%s'", issue_title)
        return prompt

    def build_f4_prompt(
        self,
        mr_description: str,
        mr_comments: str,
        branch_name: str,
        repository_url: str,
        user_f4_template: Optional[str] = None,
    ) -> str:
        """
        F-4（MR処理）用のプロンプトをテンプレートから生成する。

        ユーザー個別テンプレートがある場合はそれを優先し、
        なければシステムデフォルトの f4_prompt_template を使用する。
        変数: {mr_description}, {mr_comments}, {branch_name}, {repository_url}

        Args:
            mr_description: MR の説明文
            mr_comments: MR のコメント一覧（結合済みテキスト）
            branch_name: MR のソースブランチ名
            repository_url: リポジトリ URL
            user_f4_template: ユーザー個別 F-4 テンプレート（None の場合はシステムデフォルト使用）

        Returns:
            str: 変数展開済みのプロンプト文字列

        Raises:
            ValueError: テンプレートが存在しない場合
        """
        # ユーザー個別テンプレートを優先、なければシステムデフォルトを使用
        if user_f4_template:
            template: str = user_f4_template
            logger.debug("PromptBuilder.build_f4_prompt: ユーザー個別テンプレートを使用")
        else:
            system_template: Optional[str] = self._get_system_setting(_KEY_F4_TEMPLATE)
            if not system_template:
                raise ValueError(
                    "F-4 プロンプトテンプレートが system_settings に設定されていません。"
                )
            template = system_template
            logger.debug("PromptBuilder.build_f4_prompt: システムデフォルトテンプレートを使用")

        # テンプレート変数を展開
        prompt: str = template
        prompt = prompt.replace("{mr_description}", mr_description)
        prompt = prompt.replace("{mr_comments}", mr_comments)
        prompt = prompt.replace("{branch_name}", branch_name)
        prompt = prompt.replace("{repository_url}", repository_url)

        logger.debug("PromptBuilder.build_f4_prompt: branch_name='%s'", branch_name)
        return prompt
