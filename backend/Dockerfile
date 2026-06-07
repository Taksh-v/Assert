# Use an official lightweight Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download SpaCy English model for Presidio Analyzer (PII Scrubbing)
RUN python -m spacy download en_core_web_sm

# Copy the rest of the backend application code
COPY . /app/backend/

# Move the start script to the root of workspace context
RUN cp /app/backend/start.sh /app/start.sh && chmod +x /app/start.sh

# Run the startup script
CMD ["/app/start.sh"]
