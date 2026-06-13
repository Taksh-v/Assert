# ─────────────────────────────────────────────────────────────
# Assest Company Brain — Production Dockerfile for HF Spaces
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Non-interactive apt + disable bytecode caching
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1. Install system build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python dependencies (cached layer)
COPY backend/requirements.txt /app/requirements.txt
COPY requirements.txt /app/requirements-root.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 3. Download SpaCy English model for Presidio PII Scrubbing
RUN python -m spacy download en_core_web_sm || true

# 4. Copy application code
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/
COPY skills/ /app/skills/

# 5. Ensure data directories exist
RUN mkdir -p /app/data /app/logs

# 6. Set PYTHONPATH so `backend.*` imports resolve
ENV PYTHONPATH=/app

# 7. Expose port (HF Spaces defaults to 7860; we override via PORT env var)
EXPOSE 7860

ENV CACHE_BUST=2
# 8. Start the system: Admin creation -> Services
# We use && to ensure db is prepared before starting the API server
CMD ["bash", "-c", "python -u backend/worker_main.py & exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --log-level info"]
