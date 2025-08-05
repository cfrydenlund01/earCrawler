# syntax=docker/dockerfile:1
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt \
    bitsandbytes peft sentence-transformers faiss-cpu
CMD ["sh", "-c", "uvicorn ${APP_MODULE:-earCrawler.service.sparql_service:app} --host 0.0.0.0 --port 8000"]
