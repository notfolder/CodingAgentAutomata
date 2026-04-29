"""
GitLab API クライアントモジュール。

python-gitlab ライブラリを利用して GitLab REST API にアクセスする。
エラーハンドリング（401/403/404/429/5xx）と指数バックオフリトライを実装する。
"""

import logging
import time
from typing import Optional

import gitlab
import gitlab.exceptions

# ロガーを設定
logger = logging.getLogger(__name__)

# リトライ設定
_MAX_RETRIES = 3          # 5xx / 接続エラーの最大リトライ回数
_RATE_LIMIT_MAX_RETRIES = 5  # 429 レートリミット時の最大リトライ回数
_BASE_BACKOFF_SEC = 1.0   # バックオフ基底秒数
_MAX_BACKOFF_SEC = 60.0   # バックオフ最大待機秒数


class GitLabClient:
    """
    GitLab APIクライアント。

    python-gitlab を薄くラップし、Issue / MR / ブランチ / ユーザー操作を提供する。
    HTTPエラーコードに応じたハンドリング（401/403は例外、404はNone/スキップ、
    429は指数バックオフ、5xxはリトライ）を内包する。
    """

    def __init__(self, pat: str, api_url: str) -> None:
        """
        GitLabClient を初期化する。

        Args:
            pat: GitLab Personal Access Token（api スコープ必須）
            api_url: GitLab インスタンスのベースURL（例: https://gitlab.com）
        """
        self._gl = gitlab.Gitlab(url=api_url, private_token=pat)
        # 接続テストは行わず、実際のAPI呼び出し時に認証する
        logger.debug("GitLabClient initialized: url=%s", api_url)

    # ------------------------------------------------------------------
    # 内部ヘルパー: リトライ付き API 呼び出し
    # ------------------------------------------------------------------

    def _call_with_retry(self, func, *args, **kwargs):
        """
        指数バックオフ付きでAPIコールをリトライする。

        - 429 (Too Many Requests): 最大 _RATE_LIMIT_MAX_RETRIES 回リトライ
        - 5xx (サーバーエラー): 最大 _MAX_RETRIES 回リトライ
        - 401/403 (認証/権限エラー): 即例外送出
        - 404 (Not Found): None を返す

        Args:
            func: 呼び出す関数
            *args: funcへの位置引数
            **kwargs: funcへのキーワード引数

        Returns:
            funcの戻り値、または 404 の場合は None
        """
        last_exc: Optional[Exception] = None
        # 429 レートリミット用の独立したカウンター
        rate_limit_count: int = 0

        for attempt in range(_MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except gitlab.exceptions.GitlabHttpError as exc:
                status = exc.response_code
                if status in (401, 403):
                    # 認証エラー・権限エラーはリトライしない
                    logger.error("GitLab auth/permission error: status=%d, msg=%s", status, exc)
                    raise
                if status == 404:
                    # リソースが存在しない場合は None を返す
                    logger.debug("GitLab 404: %s", exc)
                    return None
                if status == 429:
                    # レートリミット: 独立カウンターで指数バックオフリトライ
                    rate_limit_count += 1
                    if rate_limit_count > _RATE_LIMIT_MAX_RETRIES:
                        logger.error("GitLab rate limit (429) exceeded max retries (%d)",
                                     _RATE_LIMIT_MAX_RETRIES)
                        raise
                    wait = min(_BASE_BACKOFF_SEC * (2 ** rate_limit_count), _MAX_BACKOFF_SEC)
                    logger.warning("GitLab rate limit (429), retry %d/%d in %.1fs",
                                   rate_limit_count, _RATE_LIMIT_MAX_RETRIES, wait)
                    time.sleep(wait)
                    last_exc = exc
                    # 429 はメインループのカウントを消費しない（continue でスキップ）
                    continue
                if status >= 500:
                    # サーバーエラー: 指数バックオフでリトライ
                    wait = min(_BASE_BACKOFF_SEC * (2 ** attempt), _MAX_BACKOFF_SEC)
                    logger.warning("GitLab server error (%d), retry %d/%d in %.1fs",
                                   status, attempt + 1, _MAX_RETRIES, wait)
                    time.sleep(wait)
                    last_exc = exc
                    continue
                # その他の HTTPエラーは即例外送出
                raise
            except Exception as exc:  # 接続エラーなど
                wait = min(_BASE_BACKOFF_SEC * (2 ** attempt), _MAX_BACKOFF_SEC)
                logger.warning("GitLab request error: %s, retry %d/%d in %.1fs",
                               exc, attempt + 1, _MAX_RETRIES, wait)
                time.sleep(wait)
                last_exc = exc

        # リトライ上限到達
        if last_exc:
            raise last_exc
        return None

    # ------------------------------------------------------------------
    # 内部ヘルパー: ページネーション付きリスト取得
    # ------------------------------------------------------------------

    def _list_all_pages(self, manager, **kwargs) -> list:
        """
        手動ページネーションで全件取得する。

        python-gitlab の list(all=True) は GitLab の Link ヘッダーを使ったページネーションを行うが、
        GitLab の external_url が localhost に設定されている場合、コンテナ内からの次ページ取得が
        失敗する。そのため page=1, 2, ... を明示的に指定して全件取得する。

        Args:
            manager: python-gitlab のマネージャオブジェクト（issues, mergerequests など）
            **kwargs: manager.list() に渡す追加引数

        Returns:
            取得した全アイテムのリスト
        """
        results = []
        page = 1
        per_page = 100
        while True:
            items = manager.list(page=page, per_page=per_page, **kwargs)
            results.extend(items)
            if len(items) < per_page:
                # 取得件数が per_page 未満なら最終ページ
                break
            page += 1
        return results

    # ------------------------------------------------------------------
    # Issue 操作
    # ------------------------------------------------------------------

    def get_issue(self, project_id: int, iid: int) -> Optional[dict]:
        """
        指定プロジェクトのIssueを取得する。

        Args:
            project_id: GitLabプロジェクトID
            iid: Issue の内部ID（IID）

        Returns:
            Issueの属性辞書、存在しない場合は None
        """
        def _call():
            project = self._gl.projects.get(project_id)
            issue = project.issues.get(iid)
            return issue.attributes

        result = self._call_with_retry(_call)
        return result

    def create_issue_note(self, project_id: int, iid: int, body: str) -> Optional[dict]:
        """
        Issueにコメント（Note）を投稿する。

        Args:
            project_id: GitLabプロジェクトID
            iid: Issue IID
            body: コメント本文（Markdown）

        Returns:
            作成されたNoteの属性辞書
        """
        def _call():
            project = self._gl.projects.get(project_id)
            issue = project.issues.get(iid)
            note = issue.notes.create({"body": body})
            return note.attributes

        return self._call_with_retry(_call)

    def update_issue_labels(
        self, project_id: int, iid: int, labels: list[str]
    ) -> Optional[dict]:
        """
        Issueのラベルを更新する。

        Args:
            project_id: GitLabプロジェクトID
            iid: Issue IID
            labels: 設定するラベル名のリスト

        Returns:
            更新後のIssue属性辞書
        """
        def _call():
            project = self._gl.projects.get(project_id)
            issue = project.issues.get(iid)
            issue.labels = labels
            issue.save()
            return issue.attributes

        return self._call_with_retry(_call)

    def list_issues(
        self,
        project_id: int,
        assignee_username: Optional[str] = None,
        labels: Optional[list[str]] = None,
        state: str = "opened",
    ) -> list[dict]:
        """
        プロジェクトのIssue一覧を取得する。

        Args:
            project_id: GitLabプロジェクトID
            assignee_username: アサイニーのユーザー名（省略可）
            labels: フィルタするラベルのリスト（省略可）
            state: Issueのステータス（"opened" / "closed" / "all"）

        Returns:
            Issue属性辞書のリスト
        """
        def _call():
            project = self._gl.projects.get(project_id)
            kwargs: dict = {"state": state}
            if assignee_username:
                kwargs["assignee_username"] = assignee_username
            if labels:
                kwargs["labels"] = labels
            issues = self._list_all_pages(project.issues, **kwargs)
            return [i.attributes for i in issues]

        result = self._call_with_retry(_call)
        return result if result is not None else []

    def get_issue_notes(self, project_id: int, iid: int) -> list[dict]:
        """
        Issue の全コメント（Note）一覧を取得する。

        Args:
            project_id: GitLabプロジェクトID
            iid: Issue IID

        Returns:
            Note属性辞書のリスト
        """
        def _call():
            project = self._gl.projects.get(project_id)
            issue = project.issues.get(iid)
            notes = self._list_all_pages(issue.notes)
            return [n.attributes for n in notes]

        result = self._call_with_retry(_call)
        return result if result is not None else []

    # ------------------------------------------------------------------
    # Merge Request 操作
    # ------------------------------------------------------------------

    def list_merge_requests(
        self,
        project_id: int,
        assignee_username: Optional[str] = None,
        labels: Optional[list[str]] = None,
        state: str = "opened",
    ) -> list[dict]:
        """
        プロジェクトのMR一覧を取得する。

        Args:
            project_id: GitLabプロジェクトID
            assignee_username: アサイニーのユーザー名（省略可）
            labels: フィルタするラベルのリスト（省略可）
            state: MRのステータス（"opened" / "closed" / "merged" / "all"）

        Returns:
            MR属性辞書のリスト
        """
        def _call():
            project = self._gl.projects.get(project_id)
            kwargs: dict = {"state": state}
            if assignee_username:
                kwargs["assignee_username"] = assignee_username
            if labels:
                kwargs["labels"] = labels
            mrs = self._list_all_pages(project.mergerequests, **kwargs)
            return [mr.attributes for mr in mrs]

        result = self._call_with_retry(_call)
        return result if result is not None else []

    def get_merge_request(self, project_id: int, iid: int) -> Optional[dict]:
        """
        指定プロジェクトのMRを取得する。

        Args:
            project_id: GitLabプロジェクトID
            iid: MR IID

        Returns:
            MR属性辞書、存在しない場合は None
        """
        def _call():
            project = self._gl.projects.get(project_id)
            mr = project.mergerequests.get(iid)
            return mr.attributes

        return self._call_with_retry(_call)

    def create_merge_request(
        self,
        project_id: int,
        title: str,
        source_branch: str,
        target_branch: str,
        description: str = "",
        draft: bool = True,
        reviewer_ids: Optional[list[int]] = None,
        assignee_id: Optional[int] = None,
        label_ids: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """
        新しいMRを作成する。

        Args:
            project_id: GitLabプロジェクトID
            title: MRタイトル
            source_branch: マージ元ブランチ名
            target_branch: マージ先ブランチ名
            description: MR説明文（Markdown）
            draft: Draft MR として作成するか
            reviewer_ids: レビュアーのユーザーIDリスト（省略可）
            assignee_id: アサイニーのユーザーID（省略可）
            label_ids: ラベル名のリスト（省略可）

        Returns:
            作成されたMR属性辞書
        """
        def _call():
            project = self._gl.projects.get(project_id)
            mr_title = f"Draft: {title}" if draft else title
            payload: dict = {
                "title": mr_title,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "description": description,
            }
            if reviewer_ids:
                payload["reviewer_ids"] = reviewer_ids
            if assignee_id:
                payload["assignee_id"] = assignee_id
            if label_ids:
                payload["labels"] = label_ids
            mr = project.mergerequests.create(payload)
            return mr.attributes

        return self._call_with_retry(_call)

    def update_merge_request(self, project_id: int, iid: int, **kwargs) -> Optional[dict]:
        """
        MRを更新する（任意フィールド）。

        Args:
            project_id: GitLabプロジェクトID
            iid: MR IID
            **kwargs: 更新するフィールドと値

        Returns:
            更新後のMR属性辞書
        """
        def _call():
            project = self._gl.projects.get(project_id)
            mr = project.mergerequests.get(iid)
            for key, value in kwargs.items():
                setattr(mr, key, value)
            mr.save()
            return mr.attributes

        return self._call_with_retry(_call)

    def update_merge_request_labels(
        self, project_id: int, iid: int, labels: list[str]
    ) -> Optional[dict]:
        """
        MRのラベルを更新する。

        Args:
            project_id: GitLabプロジェクトID
            iid: MR IID
            labels: 設定するラベル名のリスト

        Returns:
            更新後のMR属性辞書
        """
        return self.update_merge_request(project_id, iid, labels=labels)

    def create_merge_request_note(
        self, project_id: int, iid: int, body: str
    ) -> Optional[dict]:
        """
        MRにコメント（Note）を投稿する。

        Args:
            project_id: GitLabプロジェクトID
            iid: MR IID
            body: コメント本文（Markdown）

        Returns:
            作成されたNote属性辞書
        """
        def _call():
            project = self._gl.projects.get(project_id)
            mr = project.mergerequests.get(iid)
            note = mr.notes.create({"body": body})
            return note.attributes

        return self._call_with_retry(_call)

    def update_merge_request_note(
        self, project_id: int, iid: int, note_id: int, body: str
    ) -> Optional[dict]:
        """
        MRのコメント（Note）を更新する。

        Args:
            project_id: GitLabプロジェクトID
            iid: MR IID
            note_id: NoteのID
            body: 新しいコメント本文（Markdown）

        Returns:
            更新後のNote属性辞書
        """
        def _call():
            project = self._gl.projects.get(project_id)
            mr = project.mergerequests.get(iid)
            note = mr.notes.get(note_id)
            note.body = body
            note.save()
            return note.attributes

        return self._call_with_retry(_call)

    def get_merge_request_notes(self, project_id: int, iid: int) -> list[dict]:
        """
        MRの全コメント（Note）一覧を取得する。

        Args:
            project_id: GitLabプロジェクトID
            iid: MR IID

        Returns:
            Note属性辞書のリスト
        """
        def _call():
            project = self._gl.projects.get(project_id)
            mr = project.mergerequests.get(iid)
            notes = self._list_all_pages(mr.notes)
            return [n.attributes for n in notes]

        result = self._call_with_retry(_call)
        return result if result is not None else []

    # ------------------------------------------------------------------
    # ブランチ操作
    # ------------------------------------------------------------------

    def create_branch(
        self, project_id: int, branch_name: str, ref: str = "main"
    ) -> Optional[dict]:
        """
        新しいブランチを作成する。

        Args:
            project_id: GitLabプロジェクトID
            branch_name: 作成するブランチ名
            ref: ブランチの参照元（デフォルト: "main"）

        Returns:
            作成されたブランチ属性辞書
        """
        def _call():
            project = self._gl.projects.get(project_id)
            branch = project.branches.create({"branch": branch_name, "ref": ref})
            return branch.attributes

        return self._call_with_retry(_call)

    def branch_exists(self, project_id: int, branch_name: str) -> bool:
        """
        指定ブランチが存在するか確認する。

        Args:
            project_id: GitLabプロジェクトID
            branch_name: 確認するブランチ名

        Returns:
            存在する場合 True、存在しない場合 False
        """
        def _call():
            project = self._gl.projects.get(project_id)
            try:
                project.branches.get(branch_name)
                return True
            except gitlab.exceptions.GitlabHttpError as exc:
                if exc.response_code == 404:
                    return False
                raise

        result = self._call_with_retry(_call)
        return bool(result)

    def list_branches(self, project_id: int, max_count: int = 100) -> list[str]:
        """
        指定プロジェクトの既存ブランチ名一覧を取得する。

        Args:
            project_id: GitLabプロジェクトID
            max_count: 取得する最大件数（デフォルト: 100）

        Returns:
            ブランチ名のリスト
        """
        if max_count <= 0:
            return []

        def _call():
            project = self._gl.projects.get(project_id)
            # 全件取得するとプロンプトサイズが大きくなりやすいため、最大件数で打ち切る
            branches = project.branches.list(page=1, per_page=max_count)
            names = [b.attributes.get("name", "") for b in branches]
            return [n for n in names if n]

        result = self._call_with_retry(_call)
        return result if result is not None else []

    # ------------------------------------------------------------------
    # プロジェクト・ユーザー操作
    # ------------------------------------------------------------------

    def get_project_info(self, project_id: int) -> Optional[dict]:
        """
        プロジェクト情報を取得する。

        Args:
            project_id: GitLabプロジェクトID

        Returns:
            プロジェクト属性辞書、存在しない場合は None
        """
        def _call():
            project = self._gl.projects.get(project_id)
            return project.attributes

        return self._call_with_retry(_call)

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """
        ユーザー名からGitLabユーザー情報を取得する。

        Args:
            username: GitLabユーザー名

        Returns:
            ユーザー属性辞書、存在しない場合は None
        """
        def _call():
            users = self._gl.users.list(username=username, per_page=1, page=1)
            if not users:
                return None
            return users[0].attributes

        return self._call_with_retry(_call)
