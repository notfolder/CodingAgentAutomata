"""
GitLab イベントハンドラーモジュール。

WebhookServer またはポーリングループから受け取った GitLab イベントを解析し、
条件を満たす場合にタスクを RabbitMQ に投入する。

主要クラス:
    DuplicateCheckService: pending/running タスクの重複チェック
    GitLabEventHandler: イベント解析・タスク投入ロジック
"""

import logging
import uuid
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.config.config import Settings
from shared.models.db import Task
from shared.models.task import TaskMessage

# ロガーを設定
logger = logging.getLogger(__name__)

# アクティブ状態とみなすタスクのステータス
_ACTIVE_STATUSES = ("pending", "running")


class DuplicateCheckService:
    """
    タスク重複チェックサービス。

    tasks テーブルを参照して、同じプロジェクト・IID・タスク種別の
    pending または running タスクが既に存在するかを確認する。
    """

    def __init__(self, db_session_factory: Callable[[], Session]) -> None:
        """
        DuplicateCheckService を初期化する。

        Args:
            db_session_factory: SQLAlchemy Session を生成するファクトリ関数
        """
        self._db_session_factory = db_session_factory

    def is_duplicate(
        self,
        gitlab_project_id: int,
        source_iid: int,
        task_type: str,
    ) -> bool:
        """
        指定の条件に合致する pending または running のタスクが既に存在するか確認する。

        Args:
            gitlab_project_id: GitLabプロジェクトID
            source_iid: Issue IID または MR IID
            task_type: タスク種別（"issue" または "merge_request"）

        Returns:
            重複するタスクが存在する場合は True、そうでなければ False
        """
        with self._db_session_factory() as session:
            count = (
                session.query(Task)
                .filter(
                    Task.gitlab_project_id == gitlab_project_id,
                    Task.source_iid == source_iid,
                    Task.task_type == task_type,
                    Task.status.in_(_ACTIVE_STATUSES),
                )
                .count()
            )
        return count > 0


class GitLabEventHandler:
    """
    GitLab イベントを解析してタスクキューに投入するハンドラー。

    Webhook ペイロードまたはポーリング結果を受け取り、
    - botアサイン（GITLAB_BOT_NAME）かつ特定ラベル（GITLAB_BOT_LABEL）が揃っているか
    - 完了ラベル（GITLAB_DONE_LABEL）が付いていないか
    - 同一 Issue/MR の pending/running タスクが存在しないか
    を確認し、全条件を満たす場合のみ RabbitMQ にタスクを投入する。
    """

    def __init__(
        self,
        gitlab_client: object,
        rabbitmq_client: object,
        db_session_factory: Callable[[], Session],
        settings: Settings,
    ) -> None:
        """
        GitLabEventHandler を初期化する。

        Args:
            gitlab_client: GitLabClient インスタンス
            rabbitmq_client: RabbitMQClient インスタンス
            db_session_factory: SQLAlchemy Session ファクトリ関数
            settings: アプリケーション設定インスタンス
        """
        self._gitlab_client = gitlab_client
        self._rabbitmq_client = rabbitmq_client
        self._db_session_factory = db_session_factory
        self._settings = settings
        self._dup_check = DuplicateCheckService(db_session_factory)

    def handle_event(self, payload: dict) -> None:
        """
        Webhook イベントまたはポーリングイベントからタスクを RabbitMQ に投入する。

        Webhook ペイロードの object_kind フィールドに基づいて処理を振り分ける。
        object_kind が "issue" または "merge_request" 以外の場合はスキップする。

        Args:
            payload: GitLab Webhook ペイロード辞書
        """
        object_kind: str = payload.get("object_kind", "")

        if object_kind == "issue":
            self._handle_issue_event(payload)
        elif object_kind == "merge_request":
            self._handle_mr_event(payload)
        else:
            # Issue/MR 以外のイベント（push, note 等）はスキップ
            logger.debug("GitLabEventHandler: unsupported object_kind=%s, skip", object_kind)

    def _handle_issue_event(self, payload: dict) -> None:
        """
        Issue Webhook イベントを処理する。

        object_attributes から iid と project_id を取得し、
        assignees リストを使用してアサイン確認を行う。

        Args:
            payload: GitLab Webhook ペイロード辞書
        """
        attrs: dict = payload.get("object_attributes", {})
        iid: Optional[int] = attrs.get("iid")
        project_id: Optional[int] = attrs.get("project_id") or (
            payload.get("project", {}).get("id")
        )

        if not iid or not project_id:
            logger.warning(
                "GitLabEventHandler: Issue event missing iid or project_id, skip"
            )
            return

        # Webhook ペイロードの assignees リストを item として扱うため
        # handle_event 用の擬似 item 辞書を構築する
        item: dict = {
            "iid": iid,
            "project_id": project_id,
            # Issue の assignees は Webhook ペイロードの "assignees" キーに存在する
            "assignees": payload.get("assignees", []),
            "labels": self._extract_labels(attrs),
        }

        if not self._should_process(item, "issue"):
            return

        # Webhook ペイロードには Issue author オブジェクトが含まれないため
        # GitLab API から取得して補完する
        gitlab_issue = self._gitlab_client.get_issue(project_id, iid)
        if gitlab_issue:
            item["author"] = gitlab_issue.get("author") or {}
        else:
            logger.warning(
                "GitLabEventHandler: could not fetch Issue #%d from GitLab API, skip", iid
            )
            return

        username = self._get_username_for_task(item, "issue")
        if username is None:
            logger.warning(
                "GitLabEventHandler: could not determine username for issue #%d", iid
            )
            return

        if self._dup_check.is_duplicate(project_id, iid, "issue"):
            logger.info(
                "GitLabEventHandler: duplicate issue task project_id=%d iid=%d, skip",
                project_id,
                iid,
            )
            return

        self._enqueue_task(project_id, iid, "issue", username)

    def _handle_mr_event(self, payload: dict) -> None:
        """
        Merge Request Webhook イベントを処理する。

        object_attributes から iid と project_id を取得し、
        assignee フィールドを使用してアサイン確認を行う。

        Args:
            payload: GitLab Webhook ペイロード辞書
        """
        attrs: dict = payload.get("object_attributes", {})
        iid: Optional[int] = attrs.get("iid")
        project_id: Optional[int] = attrs.get("target_project_id") or (
            payload.get("project", {}).get("id")
        )

        if not iid or not project_id:
            logger.warning(
                "GitLabEventHandler: MR event missing iid or project_id, skip"
            )
            return

        # MR の場合は assignee が単一フィールドのため、リスト形式に統一する
        assignee: Optional[dict] = payload.get("assignee") or attrs.get("assignee")
        assignees: list[dict] = [assignee] if assignee else []

        # レビュアー一覧（ポーリングと形式を合わせるため reviewers キーに格納）
        reviewers: list[dict] = payload.get("reviewers", [])
        author: Optional[dict] = payload.get("user") or attrs.get("last_commit", {}).get(
            "author"
        )

        item: dict = {
            "iid": iid,
            "project_id": project_id,
            "assignees": assignees,
            "reviewers": reviewers,
            "author": author or {},
            "labels": self._extract_labels(attrs),
        }

        if not self._should_process(item, "merge_request"):
            return

        username = self._get_username_for_task(item, "merge_request")
        if username is None:
            logger.warning(
                "GitLabEventHandler: could not determine username for MR !%d", iid
            )
            return

        if self._dup_check.is_duplicate(project_id, iid, "merge_request"):
            logger.info(
                "GitLabEventHandler: duplicate MR task project_id=%d iid=%d, skip",
                project_id,
                iid,
            )
            return

        self._enqueue_task(project_id, iid, "merge_request", username)

    def _should_process(self, item: dict, item_type: str) -> bool:
        """
        処理対象かどうかを判定する。

        以下の条件を全て満たす場合のみ True を返す:
        - GITLAB_BOT_NAME がアサイニーに含まれている
        - GITLAB_BOT_LABEL がラベルに付与されている
        - GITLAB_DONE_LABEL がラベルに付与されていない

        Args:
            item: Issue または MR の属性辞書
            item_type: "issue" または "merge_request"

        Returns:
            処理対象の場合は True
        """
        bot_name: str = self._settings.gitlab_bot_name
        bot_label: str = self._settings.gitlab_bot_label
        done_label: str = self._settings.gitlab_done_label

        # アサイニー確認
        assignees: list[dict] = item.get("assignees", [])
        assignee_names: list[str] = [a.get("username", "") for a in assignees if a]
        if bot_name not in assignee_names:
            logger.debug(
                "GitLabEventHandler: bot '%s' not assigned to %s iid=%d, skip",
                bot_name,
                item_type,
                item.get("iid"),
            )
            return False

        # ラベル確認
        labels: list[str] = item.get("labels", [])
        if bot_label not in labels:
            logger.debug(
                "GitLabEventHandler: bot_label '%s' not found in %s iid=%d, skip",
                bot_label,
                item_type,
                item.get("iid"),
            )
            return False

        # 完了ラベル確認（付いていたらスキップ）
        if done_label and done_label in labels:
            logger.debug(
                "GitLabEventHandler: done_label '%s' found in %s iid=%d, skip",
                done_label,
                item_type,
                item.get("iid"),
            )
            return False

        return True

    def _extract_labels(self, attrs: dict) -> list[str]:
        """
        Webhook ペイロードの object_attributes からラベル名リストを抽出する。

        GitLab Webhook の labels フィールドは辞書のリストまたは文字列リストの場合がある。

        Args:
            attrs: object_attributes 辞書

        Returns:
            ラベル名文字列のリスト
        """
        raw_labels = attrs.get("labels", [])
        if not raw_labels:
            return []
        # GitLab Webhook では labels は辞書のリスト（title キー）の場合がある
        result: list[str] = []
        for label in raw_labels:
            if isinstance(label, dict):
                title = label.get("title", "")
                if title:
                    result.append(title)
            elif isinstance(label, str):
                result.append(label)
        return result

    def _get_username_for_task(self, item: dict, item_type: str) -> Optional[str]:
        """
        タスクに使用する GitLab ユーザー名を決定する。

        - Issue: author の username
        - MR: 最初のレビュアーの username、なければ author の username

        Args:
            item: Issue または MR の属性辞書
            item_type: "issue" または "merge_request"

        Returns:
            ユーザー名文字列、取得できない場合は None
        """
        if item_type == "issue":
            # Issue は author のユーザー名を使用する
            author: dict = item.get("author") or {}
            username: Optional[str] = author.get("username")
            if not username:
                logger.warning(
                    "GitLabEventHandler: Issue iid=%d has no author username",
                    item.get("iid"),
                )
            return username or None

        # MR は最初のレビュアーを優先し、なければ author を使用する
        reviewers: list[dict] = item.get("reviewers", [])
        if reviewers:
            first_reviewer_username: Optional[str] = reviewers[0].get("username")
            if first_reviewer_username:
                return first_reviewer_username

        author: dict = item.get("author") or {}
        username: Optional[str] = author.get("username")
        if not username:
            logger.warning(
                "GitLabEventHandler: MR iid=%d has no reviewer or author username",
                item.get("iid"),
            )
        return username or None

    def _enqueue_task(
        self,
        project_id: int,
        iid: int,
        task_type: str,
        username: str,
    ) -> None:
        """
        DB に pending タスクを挿入し、RabbitMQ にメッセージを投入する。

        DB への INSERT が失敗した場合（ユニーク制約違反など）はスキップする。
        RabbitMQ への publish が失敗した場合はエラーログを出力する。

        Args:
            project_id: GitLabプロジェクトID
            iid: Issue IID または MR IID
            task_type: "issue" または "merge_request"
            username: 実行対象ユーザー名
        """
        task_uuid_str = str(uuid.uuid4())

        # DB に pending タスクを挿入する
        try:
            with self._db_session_factory() as session:
                task = Task(
                    task_uuid=task_uuid_str,
                    task_type=task_type,
                    gitlab_project_id=project_id,
                    source_iid=iid,
                    username=username,
                    status="pending",
                )
                session.add(task)
                session.commit()
                logger.info(
                    "GitLabEventHandler: task inserted task_uuid=%s type=%s project=%d iid=%d",
                    task_uuid_str,
                    task_type,
                    project_id,
                    iid,
                )
        except IntegrityError as exc:
            # ユニーク制約違反 → 重複タスクとして扱い、投入をスキップする
            logger.warning(
                "GitLabEventHandler: DB insert skipped (duplicate) "
                "project_id=%d iid=%d task_type=%s: %s",
                project_id,
                iid,
                task_type,
                exc,
            )
            return
        except Exception as exc:
            # 接続エラー等の予期しない DB エラー → エラーログを出力してスキップする
            logger.error(
                "GitLabEventHandler: DB insert error project_id=%d iid=%d task_type=%s: %s",
                project_id,
                iid,
                task_type,
                exc,
                exc_info=True,
            )
            return

        # RabbitMQ にメッセージを投入する
        try:
            message = TaskMessage(
                task_uuid=task_uuid_str,
                task_type=task_type,
                gitlab_project_id=project_id,
                source_iid=iid,
                username=username,
            )
            self._rabbitmq_client.publish(message.model_dump())
            logger.info(
                "GitLabEventHandler: task enqueued task_uuid=%s type=%s project=%d iid=%d",
                task_uuid_str,
                task_type,
                project_id,
                iid,
            )
        except Exception as exc:
            logger.error(
                "GitLabEventHandler: RabbitMQ publish failed task_uuid=%s: %s",
                task_uuid_str,
                exc,
                exc_info=True,
            )

    def handle_polling_items(
        self,
        issues: list[dict],
        mrs: list[dict],
        project_id: int,
    ) -> None:
        """
        ポーリングで得た Issue/MR リストを処理する。

        各 Issue/MR に対して _should_process を確認し、条件を満たす場合のみ
        重複チェックを行ってタスクを投入する。

        Args:
            issues: ポーリングで取得した Issue 属性辞書のリスト
            mrs: ポーリングで取得した MR 属性辞書のリスト
            project_id: GitLabプロジェクトID
        """
        # Issue の処理
        for issue in issues:
            iid: Optional[int] = issue.get("iid")
            if not iid:
                continue

            # ポーリング結果の labels フィールドはラベル名文字列のリストの場合と
            # 辞書のリストの場合がある。_extract_labels で統一する
            raw_labels = issue.get("labels", [])
            labels: list[str] = self._normalize_labels(raw_labels)

            # ポーリング結果の assignees を統一形式に変換する
            assignees: list[dict] = issue.get("assignees", [])

            # author 情報
            author: dict = issue.get("author") or {}

            item: dict = {
                "iid": iid,
                "project_id": project_id,
                "assignees": assignees,
                "labels": labels,
                "author": author,
            }

            if not self._should_process(item, "issue"):
                continue

            username = self._get_username_for_task(item, "issue")
            if username is None:
                logger.warning(
                    "GitLabEventHandler: polling issue #%d has no username, skip", iid
                )
                continue

            if self._dup_check.is_duplicate(project_id, iid, "issue"):
                logger.debug(
                    "GitLabEventHandler: duplicate polling issue project_id=%d iid=%d, skip",
                    project_id,
                    iid,
                )
                continue

            self._enqueue_task(project_id, iid, "issue", username)

        # MR の処理
        for mr in mrs:
            iid_mr: Optional[int] = mr.get("iid")
            if not iid_mr:
                continue

            raw_labels_mr = mr.get("labels", [])
            labels_mr: list[str] = self._normalize_labels(raw_labels_mr)

            # MR のアサイニーは assignee（単数）または assignees（複数）が存在する
            assignees_mr: list[dict] = mr.get("assignees", [])
            single_assignee: Optional[dict] = mr.get("assignee")
            if single_assignee and not assignees_mr:
                assignees_mr = [single_assignee]

            reviewers_mr: list[dict] = mr.get("reviewers", [])
            author_mr: dict = mr.get("author") or {}

            item_mr: dict = {
                "iid": iid_mr,
                "project_id": project_id,
                "assignees": assignees_mr,
                "reviewers": reviewers_mr,
                "labels": labels_mr,
                "author": author_mr,
            }

            if not self._should_process(item_mr, "merge_request"):
                continue

            username_mr = self._get_username_for_task(item_mr, "merge_request")
            if username_mr is None:
                logger.warning(
                    "GitLabEventHandler: polling MR !%d has no username, skip", iid_mr
                )
                continue

            if self._dup_check.is_duplicate(project_id, iid_mr, "merge_request"):
                logger.debug(
                    "GitLabEventHandler: duplicate polling MR project_id=%d iid=%d, skip",
                    project_id,
                    iid_mr,
                )
                continue

            self._enqueue_task(project_id, iid_mr, "merge_request", username_mr)

    def _normalize_labels(self, raw_labels: list) -> list[str]:
        """
        ラベルリストを文字列リストに正規化する。

        GitLab API の結果では labels が文字列リストの場合と
        辞書リストの場合がある。

        Args:
            raw_labels: 正規化前のラベルリスト

        Returns:
            ラベル名文字列のリスト
        """
        result: list[str] = []
        for label in raw_labels:
            if isinstance(label, dict):
                title = label.get("title", "") or label.get("name", "")
                if title:
                    result.append(title)
            elif isinstance(label, str):
                result.append(label)
        return result
