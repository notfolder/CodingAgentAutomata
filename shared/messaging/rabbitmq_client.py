"""
RabbitMQ クライアントモジュール。

pika ライブラリを利用して RabbitMQ との接続・メッセージ送受信を行う。
接続失敗時の指数バックオフリトライを実装する。
"""

import json
import logging
import time
from typing import Callable, Optional

import pika
import pika.exceptions

# ロガーを設定
logger = logging.getLogger(__name__)

# リトライ設定
_MAX_CONNECT_RETRIES = 10    # 接続リトライ最大回数
_BASE_BACKOFF_SEC = 1.0      # バックオフ基底秒数
_MAX_BACKOFF_SEC = 60.0      # バックオフ最大待機秒数


class RabbitMQClient:
    """
    RabbitMQ クライアント。

    pika を薄くラップし、キューへのメッセージ送信と永続的な消費（consume）を提供する。
    接続失敗時は指数バックオフでリトライする。
    """

    def __init__(self, rabbitmq_url: str, queue_name: str) -> None:
        """
        RabbitMQClient を初期化する。

        Args:
            rabbitmq_url: RabbitMQ 接続URL（例: amqp://guest:guest@rabbitmq:5672/）
            queue_name: 使用するキュー名
        """
        self._rabbitmq_url = rabbitmq_url
        self._queue_name = queue_name
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        logger.debug("RabbitMQClient initialized: queue=%s", queue_name)

    def connect(self) -> None:
        """
        RabbitMQ に接続し、キューを宣言する。

        接続に失敗した場合は指数バックオフでリトライする。
        キューは durable=True で宣言し、ブローカー再起動後もキューが残る設定にする。

        Raises:
            pika.exceptions.AMQPConnectionError: リトライ上限後も接続できなかった場合
        """
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_CONNECT_RETRIES):
            try:
                params = pika.URLParameters(self._rabbitmq_url)
                self._connection = pika.BlockingConnection(params)
                self._channel = self._connection.channel()
                # durable=True でブローカー再起動後もキューが消えないよう設定
                self._channel.queue_declare(queue=self._queue_name, durable=True)
                logger.info("RabbitMQ connected: queue=%s", self._queue_name)
                return
            except pika.exceptions.AMQPConnectionError as exc:
                wait = min(_BASE_BACKOFF_SEC * (2 ** attempt), _MAX_BACKOFF_SEC)
                logger.warning(
                    "RabbitMQ connection failed, retry %d/%d in %.1fs: %s",
                    attempt + 1, _MAX_CONNECT_RETRIES, wait, exc,
                )
                time.sleep(wait)
                last_exc = exc
            except Exception as exc:
                wait = min(_BASE_BACKOFF_SEC * (2 ** attempt), _MAX_BACKOFF_SEC)
                logger.warning(
                    "RabbitMQ unexpected error, retry %d/%d in %.1fs: %s",
                    attempt + 1, _MAX_CONNECT_RETRIES, wait, exc,
                )
                time.sleep(wait)
                last_exc = exc

        # リトライ上限到達
        logger.error("RabbitMQ connection failed after %d retries", _MAX_CONNECT_RETRIES)
        if last_exc:
            raise last_exc

    def publish(self, message: dict) -> None:
        """
        メッセージをキューに送信する。

        辞書をJSONシリアライズして送信する。
        メッセージの永続化（delivery_mode=2）を有効にする。

        Args:
            message: 送信するメッセージ辞書

        Raises:
            RuntimeError: 接続されていない場合
        """
        if self._channel is None:
            raise RuntimeError("RabbitMQClient is not connected. Call connect() first.")

        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        # delivery_mode=2 でメッセージをディスク永続化
        properties = pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent,
        )
        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue_name,
            body=body,
            properties=properties,
        )
        logger.debug("RabbitMQ published: queue=%s, message=%s", self._queue_name, message)

    def consume(self, callback: Callable[[dict], None]) -> None:
        """
        キューからメッセージを永続的に消費する（ブロッキング）。

        メッセージを受信するたびに callback を呼び出す。
        callback が正常終了した場合のみ ACK を送信する。
        例外発生時は NACK を送信してメッセージをキューに戻す。

        Args:
            callback: 受信メッセージ辞書を受け取るコールバック関数

        Raises:
            RuntimeError: 接続されていない場合
        """
        if self._channel is None:
            raise RuntimeError("RabbitMQClient is not connected. Call connect() first.")

        def _on_message(ch, method, properties, body):
            """pika コールバック。JSONデコードして callback を呼び出す。"""
            try:
                message = json.loads(body.decode("utf-8"))
                logger.debug("RabbitMQ received: queue=%s, message=%s",
                             self._queue_name, message)
                callback(message)
                # 正常処理完了 → ACK
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as exc:
                logger.error("RabbitMQ callback error: %s", exc, exc_info=True)
                # エラー時は NACK してキューに戻す（requeue=True）
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        # 一度に1件ずつ処理（フェアディスパッチ）
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(queue=self._queue_name, on_message_callback=_on_message)
        logger.info("RabbitMQ start consuming: queue=%s", self._queue_name)
        self._channel.start_consuming()

    def close(self) -> None:
        """
        RabbitMQ接続を安全にクローズする。

        接続が存在しない場合は何もしない。
        """
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
                logger.info("RabbitMQ connection closed")
        except Exception as exc:
            logger.warning("RabbitMQ close error: %s", exc)
        finally:
            self._connection = None
            self._channel = None
