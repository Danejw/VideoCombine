# Base stage with common dependencies
FROM python:3.10-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security with home directory
RUN groupadd -r appuser && useradd -r -g appuser appuser -m

# Create app directories with proper permissions
RUN mkdir -p /app/tmp /app/.cache && chown -R appuser:appuser /app

# Set Hugging Face cache to app directory instead of home
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface

# Development stage
FROM base as development

# Install Python dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Switch to non-root user
USER appuser

# Expose the port
EXPOSE 8005

# Production stage
FROM base as production

# Install only production dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose the port
EXPOSE 8005

# Use Gunicorn for production
CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8005"] 