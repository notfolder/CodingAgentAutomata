# producer Dockerfile
# python:3.12-slim をベースに producer コンポーネントをインストールする
FROM python:3.12-slim

# 作業ディレクトリを設定
WORKDIR /app

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

# 作業ディレクトリを producer に移動
WORKDIR /app/producer

# producer エントリーポイント
CMD ["python", "producer.py"]
