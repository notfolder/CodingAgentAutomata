# backend Dockerfile
# python:3.12-slim をベースに backend（FastAPI）コンポーネントをインストールする
FROM python:3.12-slim

# 作業ディレクトリを設定
WORKDIR /app

# システム依存パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# shared モジュールをコピーしてインストール（backend が依存するため先にインストール）
COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared

# backend ソースをコピーしてインストール
COPY backend/ /app/backend/
RUN pip install --no-cache-dir -e /app/backend

# セットアップスクリプトをコピー
COPY scripts/setup.py /app/scripts/setup.py

# 作業ディレクトリを backend に移動
WORKDIR /app/backend

# uvicorn で FastAPI アプリを起動（ホスト 0.0.0.0、ポート 8000）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
