"""プロセス全体で共有するシャットダウン状態。"""

import threading


_shutdown_requested = threading.Event()


def request_shutdown() -> None:
    """シャットダウン要求を記録する。"""
    _shutdown_requested.set()


def reset_shutdown() -> None:
    """シャットダウン要求をクリアする。"""
    _shutdown_requested.clear()


def is_shutdown_requested() -> bool:
    """シャットダウン要求済みかを返す。"""
    return _shutdown_requested.is_set()