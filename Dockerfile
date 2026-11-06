FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY web_app.py .
COPY voice_realtime.py .
COPY voice_gemini.py .
COPY voice_supervisor.py .
COPY accounts.py .
COPY conversations.py .
COPY intelligence.py .
COPY future_lab.py .
COPY ai_council.py .
COPY file_analysis.py .
COPY web_research.py .
COPY project_memory.py .
COPY wallet.py ai_ecosystem.py .
COPY web ./web
CMD ["sh", "-c", "exec uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-10000}"]
