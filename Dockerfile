FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY web_app.py .
COPY accounts.py .
COPY conversations.py .
COPY intelligence.py .
COPY future_lab.py .
COPY ai_council.py .
COPY project_memory.py .
COPY wallet.py .
COPY web ./web
CMD ["sh", "-c", "exec uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-10000}"]
