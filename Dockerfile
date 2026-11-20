# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Only the application code (see .dockerignore: no tests, no frontend, no secrets)
COPY *.py ./

# Never run as root inside the container
RUN useradd --system --no-create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Docker (and compose) use this to know when the API is really ready
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# 1) create tables + first admin   2) start the API (exec so shutdown signals reach uvicorn)
CMD ["sh", "-c", "python create_admin.py && exec uvicorn main:app --host 0.0.0.0 --port 8000"]
