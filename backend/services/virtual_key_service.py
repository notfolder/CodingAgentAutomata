"""
Virtual Key 暗号化・復号サービスモジュール（backend用）。

AES-256-GCM アルゴリズムを使用して Virtual Key を暗号化・復号する。
暗号化鍵は ENCRYPTION_KEY 環境変数から base64 デコードして取得する。
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VirtualKeyService:
    """
    AES-256-GCM を使用した Virtual Key の暗号化・復号サービス。

    暗号化データのフォーマット: [12バイトのnonce] + [暗号文 + 16バイトのタグ]
    """

    # GCM モードで使用する nonce のバイト長
    _NONCE_LENGTH: int = 12

    def __init__(self) -> None:
        """
        初期化。

        ENCRYPTION_KEY 環境変数から base64 デコードして暗号化鍵を取得する。
        環境変数が設定されていない場合は ValueError を送出する。
        """
        raw_key = os.environ.get("ENCRYPTION_KEY", "")
        if not raw_key:
            raise ValueError(
                "ENCRYPTION_KEY 環境変数が設定されていません。"
                "base64エンコードされた32バイトの鍵を設定してください。"
            )
        # base64 デコードして AES-256-GCM 鍵として使用
        self._key: bytes = base64.b64decode(raw_key)
        if len(self._key) != 32:
            raise ValueError(
                f"ENCRYPTION_KEY は32バイト（256bit）が必要ですが、"
                f"{len(self._key)}バイトが設定されています。"
            )
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plain_text: str) -> bytes:
        """
        Virtual Key を AES-256-GCM で暗号化する。

        ランダムな12バイトの nonce を生成し、暗号文の先頭に付加して返す。
        フォーマット: nonce(12bytes) + ciphertext+tag

        Args:
            plain_text: 暗号化する平文の Virtual Key

        Returns:
            bytes: nonce + 暗号文（BYTEA として保存可能）
        """
        # ランダムな nonce を生成
        nonce = os.urandom(self._NONCE_LENGTH)
        # AES-256-GCM で暗号化（認証タグも含む）
        ciphertext = self._aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
        # nonce を先頭に付加して返す
        return nonce + ciphertext

    def decrypt(self, cipher_bytes: bytes) -> str:
        """
        AES-256-GCM で暗号化された Virtual Key を復号する。

        先頭12バイトを nonce として取り出し、残りを復号する。

        Args:
            cipher_bytes: nonce + 暗号文 のバイト列（DBから取得した値）

        Returns:
            str: 復号された平文の Virtual Key

        Raises:
            ValueError: 暗号文が不正または認証タグ検証失敗時
        """
        if len(cipher_bytes) <= self._NONCE_LENGTH:
            raise ValueError("暗号文が不正です（データが短すぎます）。")

        # 先頭12バイトを nonce として取り出す
        nonce = cipher_bytes[: self._NONCE_LENGTH]
        ciphertext = cipher_bytes[self._NONCE_LENGTH :]

        # AES-256-GCM で復号（認証タグ検証も自動的に行われる）
        plain_bytes = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plain_bytes.decode("utf-8")
