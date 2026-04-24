"""
GitLab API レスポンス用 Pydantic モデルモジュール。

GitLab REST API のレスポンスを型安全に扱うための最小限の Pydantic モデルを定義する。
extra="allow" を設定しているため、APIレスポンスの追加フィールドは無視せずに保持する。
"""

from typing import Any, Optional

from pydantic import BaseModel


class GitLabUser(BaseModel):
    """
    GitLab ユーザー情報の最小限モデル。

    Issue/MR の author・assignees・reviewers に含まれるユーザー情報を表す。
    """

    model_config = {"extra": "allow"}

    # ユーザーID
    id: int

    # ユーザー名
    username: str

    # 表示名
    name: Optional[str] = None


class GitLabIssue(BaseModel):
    """
    GitLab Issue レスポンスの最小限モデル。

    python-gitlab の issue.attributes から生成する。
    """

    model_config = {"extra": "allow"}

    # Issue グローバルID
    id: int

    # Issue 内部ID（プロジェクト内連番）
    iid: int

    # Issue タイトル
    title: str

    # Issue 説明文（Markdown）
    description: Optional[str] = None

    # Issue 作成者
    author: Optional[GitLabUser] = None

    # アサイニー一覧
    assignees: Optional[list[GitLabUser]] = None

    # ラベル名のリスト
    labels: Optional[list[str]] = None

    # GitLabプロジェクトID
    project_id: int


class GitLabMR(BaseModel):
    """
    GitLab Merge Request レスポンスの最小限モデル。

    python-gitlab の mergerequests.attributes から生成する。
    """

    model_config = {"extra": "allow"}

    # MR グローバルID
    id: int

    # MR 内部ID（プロジェクト内連番）
    iid: int

    # MR タイトル
    title: str

    # MR 説明文（Markdown）
    description: Optional[str] = None

    # MR 作成者
    author: Optional[GitLabUser] = None

    # アサイニー一覧
    assignees: Optional[list[GitLabUser]] = None

    # レビュアー一覧
    reviewers: Optional[list[Any]] = None

    # ラベル名のリスト
    labels: Optional[list[str]] = None

    # マージ元ブランチ名
    source_branch: str

    # マージ先ブランチ名
    target_branch: str

    # GitLabプロジェクトID
    project_id: int
