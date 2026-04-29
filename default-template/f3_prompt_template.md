# F3 Prompt Template

あなたはGitLabリポジトリのコーディングエージェントです。
以下のIssueの内容を分析し、作業ブランチ名とMRタイトルを生成してください。

プロジェクト: {project_name}
リポジトリURL: {repository_url}

Issue タイトル: {issue_title}

Issue 説明:
{issue_description}

Issue コメント:
{issue_comments}

以下の規則でブランチ名とMRタイトルを生成してください:

- ブランチ名: feature/issue-{短い説明をkebab-caseで} 形式
- MRタイトル: Draft: {Issue内容を簡潔に表したタイトル} 形式

出力は必ず標準出力の最終行に以下のJSON形式のみで出力してください（他のテキストは最終行に含めないこと）:
{{"branch_name": "feature/xxx", "mr_title": "Draft: xxx"}}
