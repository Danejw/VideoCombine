# Video Combine API

A FastAPI-based service that combines audio and images into videos with automatic subtitle generation using Whisper AI.

## Features

- Combine audio and images into videos
- Automatic speech-to-text transcription using Faster-Whisper
- Karaoke-style subtitles with word-level timing
- Support for both regular and short-form (9:16) videos
- Docker support for easy deployment and development


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

2. Start the service using Docker Compose:
```bash
docker-compose up --build
```

The API will be available at `http://localhost:8005`

## Development Setup

1. Build and start the development container:
```bash
docker-compose up --build
```

2. The service will automatically reload when you make changes to the code.

3. Access the API documentation at:
- Swagger UI: `http://localhost:8005/docs`
- ReDoc: `http://localhost:8005/redoc`

## API Endpoints

### 1. Combine Media (`/combine`)
Creates a video from audio and image with subtitles.

```bash
curl -X POST http://localhost:8005/combine \
  -H "Content-Type: application/json" \
  -d '{
    "audio_url": "your_audio_url",
    "image_url": "your_image_url"
  }'
```

### 2. Combine Short (`/combine-short`)
Creates a 9:16 aspect ratio video (max 59 seconds) with subtitles.

```bash
curl -X POST http://localhost:8005/combine-short \
  -H "Content-Type: application/json" \
  -d '{
    "audio_url": "your_audio_url",
    "image_url": "your_image_url"
  }'
```

## Development Commands

```bash
# Access container shell
docker-compose exec video-combine bash

# View logs
docker-compose logs -f

# Format code
docker-compose exec video-combine black .

# Run tests (if implemented)
docker-compose exec video-combine pytest
```

## Technical Details

### Dependencies
- FastAPI: Web framework
- Uvicorn: ASGI server
- Faster-Whisper: Speech recognition
- FFmpeg: Video processing
- Pydantic: Data validation

### File Processing
- Temporary files are stored in the `tmp` directory
- Files are automatically cleaned up after processing
- The `tmp` directory is mounted as a volume in Docker

### Subtitle Generation
- Uses Faster-Whisper for speech recognition
- Supports both ASS (karaoke) and SRT formats
- Word-level timing for precise synchronization

## Production Deployment

For production deployment:

1. Update the Docker Compose file to use the production target:
```yaml
services:
  video-combine:
    build:
      target: production
```

2. Set appropriate environment variables:
```yaml
environment:
  - ENVIRONMENT=production
```

## Troubleshooting

### Common Issues

1. **FFmpeg not found**
   - Ensure the Docker build completed successfully
   - Check if FFmpeg is properly installed in the container

2. **Memory Issues**
   - The transcription process can be memory-intensive
   - Consider increasing Docker memory limits if needed

3. **Timeout Errors**
   - Default timeout is 5 minutes
   - Adjust the timeout in `main.py` if needed

### Logs

View detailed logs using:
```bash
docker-compose logs -f
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