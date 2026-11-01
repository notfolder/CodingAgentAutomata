# ============================================================
# フロントエンドビルドステージ
# ============================================================
FROM node:20-alpine AS builder

# Zscaler の証明書を OS の信頼先に入れる（外へ出る最初の処理より前。無効なら何もしない）
RUN --mount=type=bind,from=zscaler,target=/zscaler sh /zscaler/install-ca.sh
# npm の信頼先を OS の証明書の束に向ける
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# 依存関係のインストール（キャッシュ最適化）
# package-lock.json に固定された版をそのまま入れる（依存解決を省けるため npm install より速く、版も再現できる）
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

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
