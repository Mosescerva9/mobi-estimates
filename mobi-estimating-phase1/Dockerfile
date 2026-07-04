FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MOBI_DB_PATH=/app/data/mobi.db \
    MOBI_UPLOAD_DIR=/app/data/uploads

WORKDIR /app

RUN addgroup --system mobi && adduser --system --ingroup mobi mobi

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

# Create the data directory owned by the unprivileged user. Docker initializes a
# fresh named volume mounted at /app/data with this directory's ownership, so the
# 'mobi' user retains write access to uploads and the SQLite database.
RUN mkdir -p /app/data/uploads && chown -R mobi:mobi /app

USER mobi

EXPOSE 8000

# Container-native health check using only the standard library (no curl needed).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else sys.exit(1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
