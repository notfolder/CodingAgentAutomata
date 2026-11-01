# producer Dockerfile
# python:3.12-slim をベースに producer コンポーネントをインストールする
FROM python:3.12-slim

# 作業ディレクトリを設定
WORKDIR /app

# Zscaler の証明書を OS の信頼先に入れる（外へ出る最初の処理より前。無効なら何もしない）
RUN --mount=type=bind,from=zscaler,target=/zscaler sh /zscaler/install-ca.sh
# 各ツールの信頼先を OS の証明書の束に向ける（Zscaler 設定の有効・無効によらない）
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# システム依存パッケージのインストール（psycopg2-binary に必要な libpq-dev は不要だが build-essential は念のため）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# shared モジュールをコピーしてインストール（producer が依存するため先にインストール）
COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared

# producer ソースをコピーしてインストール
COPY producer/ /app/producer/
RUN pip install --no-cache-dir -e /app/producer

# 作業ディレクトリを /app に維持（パッケージとして実行するため）
WORKDIR /app

# producer エントリーポイント（-m でパッケージとして実行して名前衝突を回避）
CMD ["python", "-m", "producer.producer"]
