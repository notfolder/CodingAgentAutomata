"""証明書の検証を無効にする設定が、リポジトリに無いことを確かめる単体テスト。"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 証明書の検証を無効にする設定
_FORBIDDEN = [
    re.compile(r"verify\s*=\s*False"),
    re.compile(r"NODE_TLS_REJECT_UNAUTHORIZED"),
    re.compile(r"ignoreHTTPSErrors"),
    re.compile(r"curl\s[^\n]*(--insecure|\s-k\s)"),
    re.compile(r"--trusted-host"),
    re.compile(r"ssl_verify\s*:\s*false", re.IGNORECASE),
]
# 調べないディレクトリ（依存物、仮想環境、変更の記録、文書）
_SKIP_DIRS = {"node_modules", ".git", ".history", "docs", ".zscaler", "__pycache__", "dist"}
_SUFFIXES = {".py", ".ts", ".js", ".vue", ".sh", ".yml", ".yaml", ".json", ".toml", ".conf", ""}


def _files():
    """調べるファイルを返す。"""
    for path in REPO.rglob("*"):
        rel = path.relative_to(REPO)
        if any(part in _SKIP_DIRS or part.startswith(".venv") for part in rel.parts):
            continue
        if not path.is_file() or path.suffix not in _SUFFIXES:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        yield path


def test_no_tls_verification_disabled() -> None:
    """どのファイルにも、証明書の検証を無効にする設定が無いこと。"""
    found = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in _FORBIDDEN:
            if pattern.search(text):
                found.append(f"{path.relative_to(REPO)}: {pattern.pattern}")
    assert found == []
