# mock-llm Dockerfile
# Python 軽量イメージで OpenAI / LiteLLM 互換モック LLM サーバーを提供する
FROM python:3.12-slim

WORKDIR /app

COPY server.py .

EXPOSE 4000

CMD ["python", "server.py"]
