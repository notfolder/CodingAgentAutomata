# consumer Dockerfile
# python:3.12-slim をベースに consumer コンポーネントをインストールする
# Docker SDK（docker>=7.0）が必要なため docker.sock をマウントして利用する
FROM python:3.12-slim AS runtime

# 作業ディレクトリを設定
WORKDIR /app

# Zscaler の証明書を OS の信頼先に入れる（外へ出る最初の処理より前。無効なら何もしない）
RUN --mount=type=bind,from=zscaler,target=/zscaler sh /zscaler/install-ca.sh
# 各ツールの信頼先を OS の証明書の束に向ける（Zscaler 設定の有効・無効によらない）
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# システム依存パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# shared モジュールをコピーしてインストール（consumer が依存するため先にインストール）
COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared

# consumer ソースをコピーしてインストール
COPY consumer/ /app/consumer/
RUN pip install --no-cache-dir -e /app/consumer

# 作業ディレクトリを /app に維持（パッケージとして実行するため）
WORKDIR /app

# consumer エントリーポイント（-m でパッケージとして実行して名前衝突を回避）
CMD ["python", "-m", "consumer.consumer"]

# ============================================================
# テスト段（単体テスト・結合テスト用。本番のイメージには入れない）
# ============================================================
FROM runtime AS test
RUN pip install --no-cache-dir pytest==9.2.0
WORKDIR /repo
CMD ["python", "-m", "pytest", "/repo/tests", "-q", "-p", "no:cacheprovider"]
