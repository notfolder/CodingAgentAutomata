# ============================================================
# フロントエンドビルドステージ
# ============================================================
FROM node:20-alpine AS builder

WORKDIR /app

# 依存関係のインストール（キャッシュ最適化）
COPY frontend/package.json ./
RUN npm install

# ソースコードのコピーとビルド
COPY frontend/ .
RUN npm run build

# ============================================================
# nginx 配信ステージ
# ============================================================
FROM nginx:stable-alpine

# ビルド成果物をコピー
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx 設定をコピー
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
