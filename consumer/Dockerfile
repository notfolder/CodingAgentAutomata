# consumer Dockerfile
# python:3.12-slim をベースに consumer コンポーネントをインストールする
# Docker SDK（docker>=7.0）が必要なため docker.sock をマウントして利用する
FROM python:3.12-slim

# 作業ディレクトリを設定
WORKDIR /app

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

# 作業ディレクトリを consumer に移動
WORKDIR /app/consumer

# consumer エントリーポイント
CMD ["python", "consumer.py"]
