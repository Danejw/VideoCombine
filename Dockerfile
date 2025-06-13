# Development stage
FROM python:3.10-slim as development

# Set working directory
WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create tmp directory
RUN mkdir -p /app/tmp

# Expose the port
EXPOSE 8005

# Production stage
FROM development as production

# Copy the application code
COPY . .

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"] 