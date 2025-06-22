# Video Combine API

A FastAPI-based service that combines audio and images into videos with automatic subtitle generation using Whisper AI.

## Features

- Combine audio and images into videos
- Automatic speech-to-text transcription using Faster-Whisper
- Karaoke-style subtitles with word-level timing
- Support for both regular and short-form (9:16) videos
- Production-ready Docker deployment with health monitoring
- Development environment with hot-reload


## Project Structure

├── main.py # Main FastAPI application
├── Dockerfile # Docker configuration
├── docker-compose.yml # Docker Compose configuration
├── requirements.txt # Production dependencies
├── requirements-dev.txt # Development dependencies
├── tmp/ # Temporary file storage
└── README.md # This file

## Prerequisites

- Docker Desktop
- Git
- Python 3.10+ (for local development)

## Quick Start

1. Clone the repository:
```bash
git clone <repository-url>
cd video-combine
```

2. **Production Deployment:**
```bash
# Build and start in production mode
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

3. **Development Setup:**
```bash
# Create development override file first (see Development section)
# Then run in development mode
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d --build
```

The API will be available at `http://localhost:8005`

## Development Setup

1. Create a `docker-compose.override.yml` file for development:
```yaml
version: '3.8'

services:
  video-combine:
    build:
      target: development
    volumes:
      - .:/app  # Mount for live updates
    command: uvicorn main:app --host 0.0.0.0 --port 8005 --reload
    environment:
      - ENVIRONMENT=development
```

2. Build and start the development container:
```bash
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d --build
```

3. The service will automatically reload when you make changes to the code.

4. Access the API documentation at:
- Swagger UI: `http://localhost:8005/docs`
- ReDoc: `http://localhost:8005/redoc`
- Health Check: `http://localhost:8005/health`

## API Endpoints

### 1. Health Check (`/health`)
Check if the service is running properly.

```bash
curl http://localhost:8005/health
```

### 2. Combine Media (`/combine`)
Creates a video from audio and image with subtitles.

```bash
curl -X POST http://localhost:8005/combine \
  -H "Content-Type: application/json" \
  -d '{
    "audio_url": "your_audio_url",
    "image_url": "your_image_url"
  }'
```

### 3. Combine Short (`/combine-short`)
Creates a 9:16 aspect ratio video (max 59 seconds) with subtitles.

```bash
curl -X POST http://localhost:8005/combine-short \
  -H "Content-Type: application/json" \
  -d '{
    "audio_url": "your_audio_url",
    "image_url": "your_image_url"
  }'
```

## Production vs Development

### Production Mode
- Uses Gunicorn with multiple workers for better performance
- Optimized Docker image with production dependencies only
- Resource limits and security configurations
- Persistent logging and health monitoring

```bash
# Production commands
docker-compose up -d                    # Start in background
docker-compose ps                       # Check status
docker-compose logs -f                  # View logs
docker-compose restart                  # Restart service
docker-compose down                     # Stop and remove containers
```

### Development Mode
- Uses Uvicorn with hot-reload
- Full development dependencies
- Volume mounting for live code updates

```bash
# Development commands
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
docker-compose -f docker-compose.yml -f docker-compose.override.yml logs -f
docker-compose -f docker-compose.yml -f docker-compose.override.yml down
```

## Development Commands

```bash
# Access container shell
docker-compose exec video-combine bash

# View real-time logs
docker-compose logs -f video-combine

# Restart specific service
docker-compose restart video-combine

# Check container health
docker-compose ps
docker inspect $(docker-compose ps -q video-combine)

# Clean up resources
docker-compose down --volumes --remove-orphans
docker system prune

# Format code (if in development mode)
docker-compose exec video-combine black .

# Run tests (if implemented)
docker-compose exec video-combine pytest
```

## Monitoring and Health

The production setup includes:
- Health checks every 30 seconds
- Automatic restart on failure
- Resource monitoring and limits
- Structured logging with rotation

```bash
# Check health status
curl http://localhost:8005/health

# Monitor resource usage
docker stats $(docker-compose ps -q)

# View container logs with timestamps
docker-compose logs -f --timestamps
```

## Production Deployment

The Docker setup is production-ready with:

1. **Security Features:**
   - Non-root user execution
   - Security options enabled
   - Network isolation

2. **Performance Optimizations:**
   - Gunicorn with multiple workers
   - Resource limits and reservations
   - Optimized Docker layers

3. **Monitoring:**
   - Health checks with automatic restart
   - Log rotation and management
   - Resource usage limits

### Environment Variables
```yaml
environment:
  - ENVIRONMENT=production
  - WORKERS=4                    # Number of Gunicorn workers
  - PYTHONUNBUFFERED=1          # Python output buffering
```

## Troubleshooting

### Common Issues

1. **Container won't start**
   ```bash
   # Check logs
   docker-compose logs video-combine
   
   # Check health status
   docker-compose ps
   ```

2. **Build takes too long**
   - Use Docker layer caching
   - Check internet connection
   - Consider using Docker registry mirror

3. **Health check failures**
   ```bash
   # Test health endpoint manually
   curl http://localhost:8005/health
   
   # Check if service is binding to correct port
   docker-compose exec video-combine netstat -tlpn
   ```

4. **Memory Issues**
   - Monitor with: `docker stats`
   - Adjust memory limits in docker-compose.yml
   - Consider reducing number of workers

### Performance Monitoring
```bash
# Resource usage
docker stats $(docker-compose ps -q)

# Container inspection
docker inspect $(docker-compose ps -q video-combine)

# Network connectivity
docker-compose exec video-combine curl -f http://localhost:8005/health
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Your License Here]

## Support

[Your Support Information Here] 