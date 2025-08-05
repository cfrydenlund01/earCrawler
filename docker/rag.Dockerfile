# syntax=docker/dockerfile:1
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt \
    bitsandbytes peft sentence-transformers faiss-cpu
CMD ["python", "-m", "earCrawler.rag.retriever"]
