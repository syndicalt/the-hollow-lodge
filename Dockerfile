FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV HOLLOW_LODGE_DATA_DIR=/data

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.115" \
    "httpx>=0.27" \
    "mcp>=1.0" \
    "openai>=1.0" \
    "psycopg[binary]>=3.2" \
    "pydantic>=2.8" \
    "typer>=0.12" \
    "uvicorn>=0.30"

COPY src ./src

EXPOSE 8000

CMD ["sh", "-c", "uvicorn hollow_lodge.server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
