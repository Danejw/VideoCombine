import os
import subprocess
import re
import platform
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uvicorn
from faster_whisper import WhisperModel

app = FastAPI()

# Add CORS middleware to allow requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Load the whisper model at startup
model_size = "base"
# Using "auto" for device selection, it will use "cuda" if available.
# Forcing CPU device to avoid CUDA/cuDNN dependency issues.
whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")

def transcribe_audio(audio_path: str):
    """Transcribes the audio file using faster-whisper."""
    segments, info = whisper_model.transcribe(audio_path, word_timestamps=True)
    print(f"Detected language '{info.language}' with probability {info.language_probability}")
    return list(segments)

def format_time_ass(seconds: float) -> str:
    """Formats time for ASS subtitle format (H:MM:SS.ss)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def words_to_karaoke_ass(segments, output_path: str, max_time: float = None):
    """Generates an ASS file with karaoke-style word timings."""
    ass_header = f"""[Script Info]
Title: Karaoke Subtitles - Enhanced Timing
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Segoe UI,48,&H00FFFFFF,&H0087CEEB,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,10,10,60,1
Style: Karaoke,Segoe UI,48,&H00FFFFFF,&H0087CEEB,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,10,10,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        for segment in segments:
            if max_time and segment.start > max_time:
                continue

            if not hasattr(segment, 'words') or not segment.words:
                continue

            start_time_ass = format_time_ass(segment.start)
            end_time_ass = format_time_ass(segment.end)

            karaoke_line = ""
            for word in segment.words:
                duration_cs = int((word.end - word.start) * 100)
                karaoke_line += f"{{\\k{duration_cs}}}{word.word}"
            
            # The first word of a segment from whisper might not have a leading space, so we trim the whole line.
            line = f"Dialogue: 0,{start_time_ass},{end_time_ass},Karaoke,,0,0,0,,{karaoke_line.strip()}"
            f.write(line + "\n")

def format_time_srt(seconds: float) -> str:
    """Formats time for SRT subtitle format (HH:MM:SS,ms)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def create_enhanced_srt(segments, output_path: str, max_time: float = None):
    """Generates an SRT file from transcription segments."""
    with open(output_path, "w", encoding="utf-8") as f:
        i = 1
        for segment in segments:
            if max_time and segment.start > max_time:
                continue
            
            start_time_srt = format_time_srt(segment.start)
            end_time_srt = format_time_srt(segment.end)
            text = segment.text.strip()
            
            f.write(f"{i}\n")
            f.write(f"{start_time_srt} --> {end_time_srt}\n")
            f.write(f"{text}\n\n")
            i += 1


class CombineRequest(BaseModel):
    audio_url: str
    image_url: str

class CombineShortRequest(BaseModel):
    audio_url: str
    image_url: str


def download_google_drive_file(url, output_path):
    """Download file from Google Drive with comprehensive handling"""
    print(f"Downloading from Google Drive: {url}")
    
    # Extract file ID from URL
    file_id = extract_file_id_from_url(url)
    if not file_id:
        print("ERROR: Could not extract file ID from URL")
        return False
    
    print(f"Extracted file ID: {file_id}")
    
    # Create a session to handle cookies and redirects
    session = requests.Session()
    
    # Try multiple download approaches
    download_urls = [
        url,  # Original URL
        f"https://drive.google.com/uc?export=download&id={file_id}",
        f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t",
        f"https://docs.google.com/uc?export=download&id={file_id}",
    ]
    
    for attempt, download_url in enumerate(download_urls, 1):
        print(f"Attempt {attempt}: Trying URL: {download_url}")
        
        try:
            # First request to get the file
            response = session.get(download_url, stream=True, timeout=30, allow_redirects=True)
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            print(f"Content type: {content_type}")
            
            # If it's HTML, we might have a virus scan warning or other issue
            if 'text/html' in content_type:
                response_text = response.text[:1000]  # First 1000 chars
                print(f"HTML Response (first 1000 chars): {response_text}")
                
                # Check for virus scan warning
                if 'virus scan warning' in response_text.lower() or 'download_warning' in response_text:
                    print("Detected virus scan warning, looking for bypass...")
                    
                    # Look for download link in the page
                    import re
                    download_link_match = re.search(r'href="(/uc\?export=download[^"]*)"', response_text)
                    if download_link_match:
                        bypass_url = "https://drive.google.com" + download_link_match.group(1).replace('&amp;', '&')
                        print(f"Found bypass URL: {bypass_url}")
                        
                        response = session.get(bypass_url, stream=True, timeout=30)
                        response.raise_for_status()
                        content_type = response.headers.get('content-type', '').lower()
                        print(f"Bypass response content type: {content_type}")
                
                # If still HTML, this attempt failed
                if 'text/html' in content_type:
                    print(f"Attempt {attempt} failed - still getting HTML")
                    continue
            
            # Check if we have actual file content
            content_length = response.headers.get('content-length')
            if content_length:
                print(f"Content length: {content_length} bytes")
            
            # Write the file
            print(f"Writing file to: {output_path}")
            with open(output_path, 'wb') as f:
                total_written = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_written += len(chunk)
            
            print(f"Successfully downloaded {total_written} bytes")
            
            # Verify the file was written
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                print(f"File verification failed for attempt {attempt}")
                continue
                
        except Exception as e:
            print(f"Attempt {attempt} failed with error: {e}")
            continue
    
    print("All download attempts failed")
    return False

def extract_file_id_from_url(url):
    """Extract file ID from Google Drive URL"""
    patterns = [
        r'id=([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
        r'file/d/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def download_file(url, output_path):
    """Download file with proper handling for different URL types"""
    print(f"Starting download: {url}")
    print(f"Output path: {output_path}")
    
    if 'drive.google.com' in url:
        return download_google_drive_file(url, output_path)
    else:
        # Regular download
        try:
            print("Regular download method...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            print(f"Response status: {response.status_code}")
            print(f"Content length: {len(response.content)} bytes")
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            print(f"File written successfully")
            return True
        except Exception as e:
            print(f"Regular download error: {e}")
            return False

def verify_file(file_path, file_type):
    """Verify downloaded file is valid"""
    print(f"Verifying {file_type} file: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"ERROR: {file_type} file does not exist: {file_path}")
        return False
    
    file_size = os.path.getsize(file_path)
    print(f"{file_type} file size: {file_size} bytes")
    
    if file_size == 0:
        print(f"ERROR: {file_type} file is empty")
        return False
    
    # Check if it's an HTML error page
    with open(file_path, 'rb') as f:
        first_bytes = f.read(500)  # Read more bytes to check
        print(f"First 50 bytes (hex): {first_bytes[:50].hex()}")
        print(f"First 200 chars: {first_bytes[:200]}")
        
        if b'<html' in first_bytes.lower() or b'<!doctype' in first_bytes.lower():
            print(f"ERROR: {file_type} file appears to be HTML (download failed)")
            return False
    
    print(f"{file_type} file verification passed")
    return True

async def process_video(audio_path, image_path, video_path, subs_path=None):
    """Common video processing logic - simplified without progress tracking"""
    ffmpeg_path = get_ffmpeg_path()
    
    # Test if ffmpeg is available
    try:
        result = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise Exception(f"FFmpeg test failed with return code {result.returncode}")
        print(f"✅ FFmpeg found and working: {ffmpeg_path}")
        print(f"FFmpeg version info: {result.stdout.split(chr(10))[0]}")  # First line only
    except Exception as e:
        print(f"ERROR: FFmpeg test failed: {e}")
        raise Exception(f"FFmpeg executable not available: {ffmpeg_path}")

    # FFmpeg command - simplified
    cmd = [
        ffmpeg_path,
        "-y",  # Overwrite output files
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
    ]
    
    if subs_path and os.path.exists(subs_path):
        # Add subtitles to the command
        # Use a complex filter to burn subtitles on top of the video
        cmd.extend(["-vf", f"subtitles='{subs_path.replace(os.sep, '/')}'"])

    cmd.append(video_path)
    
    print("\n" + "=" * 30)
    print("STARTING VIDEO GENERATION")
    print("=" * 30)
    print(f"Command: {' '.join(cmd)}")
    print(f"🎬 FFmpeg executable: {ffmpeg_path}")
    print(f"🎵 Audio file: {audio_path}")
    print(f"🖼️ Image file: {image_path}")
    print(f"🎥 Output file: {video_path}")
    
    if subs_path and os.path.exists(subs_path):
        print(f"📜 Subtitles file: {subs_path}")

    try:
        # Use subprocess.run for simple execution
        print("Running FFmpeg... (this may take a few moments)")
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=300  # 5 minute timeout
        )
        
        print(f"FFmpeg return code: {result.returncode}")
        
        # Always log stdout and stderr for debugging
        if result.stdout:
            print("FFmpeg stdout:")
            print(result.stdout)
        
        if result.stderr:
            print("FFmpeg stderr:")
            print(result.stderr)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg failed with return code {result.returncode}"
            if result.stderr:
                error_msg += f"\nSTDERR: {result.stderr}"
            if result.stdout:
                error_msg += f"\nSTDOUT: {result.stdout}"
            raise Exception(error_msg)
        
        # Verify output file
        if not os.path.exists(video_path):
            raise Exception("Output video file was not created")
            
        video_size = os.path.getsize(video_path)
        if video_size == 0:
            raise Exception("Output video file is empty")
            
        print(f"✅ Video generation completed successfully!")
        print(f"📁 Output file: {video_path}")
        print(f"📊 File size: {video_size:,} bytes ({video_size / 1024 / 1024:.2f} MB)")
        
    except subprocess.TimeoutExpired:
        print("FFmpeg process timed out after 5 minutes")
        raise Exception("Video generation timed out")
    except Exception as e:
        print(f"FFmpeg error: {e}")
        # Don't wrap the exception again if it already contains FFmpeg details
        if "FFmpeg failed with return code" in str(e):
            raise e
        else:
            raise Exception(f"Video generation failed: {e}")

    # Return the video file
    return FileResponse(video_path, media_type="video/mp4", filename="output.mp4")

async def process_video_short(audio_path, image_path, video_path, subs_path=None):
    """Process video for 9:16 aspect ratio with 59 second limit"""
    ffmpeg_path = get_ffmpeg_path()
    
    # Test if ffmpeg is available
    try:
        result = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise Exception(f"FFmpeg test failed with return code {result.returncode}")
        print(f"✅ FFmpeg found and working: {ffmpeg_path}")
        print(f"FFmpeg version info: {result.stdout.split(chr(10))[0]}")  # First line only
    except Exception as e:
        print(f"ERROR: FFmpeg test failed: {e}")
        raise Exception(f"FFmpeg executable not available: {ffmpeg_path}")

    # FFmpeg command for 9:16 vertical video, 59 seconds max
    cmd = [
        ffmpeg_path,
        "-y",  # Overwrite output files
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", "59",  # Limit duration to 59 seconds
    ]
    
    # Filter for scaling, padding, and subtitles
    video_filter = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    if subs_path and os.path.exists(subs_path):
        # Add subtitles to the filter chain. Note: Windows paths need escaping.
        escaped_path = subs_path.replace('\\', '/').replace(':', '\\:')
        video_filter += f",subtitles='{escaped_path}'"
        print(f"📜 Subtitles file: {subs_path}")

    cmd.extend([
        "-vf", video_filter,
        "-pix_fmt", "yuv420p",
        video_path
    ])
    
    print("\n" + "=" * 30)
    print("STARTING SHORT VIDEO GENERATION (9:16, 59s)")
    print("=" * 30)
    print(f"Command: {' '.join(cmd)}")
    
    try:
        # Use subprocess.run for simple execution
        print("Running FFmpeg for short video... (this may take a few moments)")
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=300  # 5 minute timeout
        )
        
        print(f"FFmpeg return code: {result.returncode}")
        
        # Always log stdout and stderr for debugging
        if result.stdout:
            print("FFmpeg stdout:")
            print(result.stdout)
        
        if result.stderr:
            print("FFmpeg stderr:")
            print(result.stderr)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg failed with return code {result.returncode}"
            if result.stderr:
                error_msg += f"\nSTDERR: {result.stderr}"
            if result.stdout:
                error_msg += f"\nSTDOUT: {result.stdout}"
            raise Exception(error_msg)
        
        # Verify output file
        if not os.path.exists(video_path):
            raise Exception("Output video file was not created")
            
        video_size = os.path.getsize(video_path)
        if video_size == 0:
            raise Exception("Output video file is empty")
            
        print(f"✅ Short video generation completed successfully!")
        print(f"📁 Output file: {video_path}")
        print(f"📊 File size: {video_size:,} bytes ({video_size / 1024 / 1024:.2f} MB)")
        print(f"📺 Format: 9:16 aspect ratio, max 59 seconds")
        
    except subprocess.TimeoutExpired:
        print("FFmpeg process timed out after 5 minutes")
        raise Exception("Video generation timed out")
    except Exception as e:
        print(f"FFmpeg error: {e}")
        # Don't wrap the exception again if it already contains FFmpeg details
        if "FFmpeg failed with return code" in str(e):
            raise e
        else:
            raise Exception(f"Video generation failed: {e}")

    # Return the video file
    return FileResponse(video_path, media_type="video/mp4", filename="output_short.mp4")

@app.post("/combine")
async def combine_media(request: CombineRequest):
    print("=" * 50)
    print("NEW REQUEST STARTED")
    print("=" * 50)
    print("request", request)

    audio_url = request.audio_url
    image_url = request.image_url

    # Ensure tmp directory exists
    tmp_dir = "./tmp"
    os.makedirs(tmp_dir, exist_ok=True)

    audio_path = os.path.join(tmp_dir, "audio.mp3")
    image_path = os.path.join(tmp_dir, "image.jpg")
    video_path = os.path.join(tmp_dir, "output.mp4")
    subs_path_ass = os.path.join(tmp_dir, "kara.ass")
    subs_path_srt = os.path.join(tmp_dir, "kara.srt")

    # Remove existing files
    for path in [audio_path, image_path, video_path, subs_path_ass, subs_path_srt]:
        if os.path.exists(path):
            os.remove(path)
            print(f"Removed existing file: {path}")

    try:
        # Download audio
        print("\n" + "=" * 30)
        print("DOWNLOADING AUDIO")
        print("=" * 30)
        if not download_file(audio_url, audio_path):
            raise Exception("Failed to download audio file")

        if not verify_file(audio_path, "Audio"):
            raise Exception("Audio download failed or file is invalid")

        # Download image
        print("\n" + "=" * 30)
        print("DOWNLOADING IMAGE")
        print("=" * 30)
        if not download_file(image_url, image_path):
            raise Exception("Failed to download image file")

        if not verify_file(image_path, "Image"):
            raise Exception("Image download failed or file is invalid")

    except Exception as e:
        print(f"Download error: {e}")
        raise Exception(f"Failed to download files: {e}")

    # Transcribe and build subtitles
    print("\n" + "=" * 30)
    print("GENERATING SUBTITLES")
    print("=" * 30)
    subs_path = None
    try:
        print("🎯 Step 1: Transcribing audio...")
        segments = transcribe_audio(audio_path)
        
        print("🎯 Step 2: Converting to subtitle formats...")
        # Try ASS format first (for karaoke effects)
        try:
            words_to_karaoke_ass(segments, subs_path_ass)
            subs_path = subs_path_ass
            print("✅ ASS subtitles generated successfully")
        except Exception as ass_error:
            print(f"⚠️ ASS generation failed: {ass_error}")
            # Fallback to enhanced SRT format
            create_enhanced_srt(segments, subs_path_srt)
            subs_path = subs_path_srt
            print("✅ SRT subtitles generated as fallback")
            
    except Exception as e:
        print(f"⚠️ Subtitle generation failed: {e}")
        print("   📝 Error details:", str(e))
        print("   🔄 Proceeding without subtitles...")
        subs_path = None

    print("\n" + "=" * 30)
    print("STARTING VIDEO PROCESSING")
    print("=" * 30)
    
    return await process_video(audio_path, image_path, video_path, subs_path)

@app.post("/combine-short")
async def combine_media_short(request: CombineShortRequest):
    print("=" * 50)
    print("NEW SHORT VIDEO REQUEST STARTED")
    print("=" * 50)
    print("request", request)
    
    audio_url = request.audio_url
    image_url = request.image_url
    
    # Validate URLs are provided
    if not audio_url or not audio_url.strip():
        raise Exception("Audio URL is required and cannot be empty")
    
    if not image_url or not image_url.strip():
        raise Exception("Image URL is required and cannot be empty")
    
    # Basic URL validation
    if not (audio_url.startswith('http://') or audio_url.startswith('https://')):
        raise Exception("Audio URL must start with http:// or https://")
        
    if not (image_url.startswith('http://') or image_url.startswith('https://')):
        raise Exception("Image URL must start with http:// or https://")
    
    print(f"Audio URL: {audio_url}")
    print(f"Image URL: {image_url}")
    
    # Ensure tmp directory exists
    tmp_dir = "./tmp"
    os.makedirs(tmp_dir, exist_ok=True)

    audio_path = os.path.join(tmp_dir, "audio_short.mp3")
    image_path = os.path.join(tmp_dir, "image_short.jpg")
    video_path = os.path.join(tmp_dir, "output_short.mp4")
    subs_path_ass = os.path.join(tmp_dir, "kara_short.ass")
    subs_path_srt = os.path.join(tmp_dir, "kara_short.srt")

    # Remove existing files
    for path in [audio_path, image_path, video_path, subs_path_ass, subs_path_srt]:
        if os.path.exists(path):
            os.remove(path)
            print(f"Removed existing file: {path}")

    try:
        # Download audio
        print("\n" + "=" * 30)
        print("DOWNLOADING AUDIO")
        print("=" * 30)
        if not download_file(audio_url, audio_path):
            raise Exception("Failed to download audio file")
        
        if not verify_file(audio_path, "Audio"):
            raise Exception("Audio download failed or file is invalid")

        # Download image
        print("\n" + "=" * 30)
        print("DOWNLOADING IMAGE")
        print("=" * 30)
        if not download_file(image_url, image_path):
            raise Exception("Failed to download image file")
            
        if not verify_file(image_path, "Image"):
            raise Exception("Image download failed or file is invalid")
            
    except Exception as e:
        print(f"Download error: {e}")
        raise Exception(f"Failed to download files: {e}")
        
    # Transcribe and build subtitles
    print("\n" + "=" * 30)
    print("GENERATING SUBTITLES")
    print("=" * 30)
    subs_path = None
    try:
        print("🎯 Step 1: Transcribing audio...")
        segments = transcribe_audio(audio_path)
        
        print("🎯 Step 2: Converting to subtitle formats (59s limit)...")
        # Try ASS format first (for karaoke effects)
        try:
            words_to_karaoke_ass(segments, subs_path_ass, max_time=59.0)
            subs_path = subs_path_ass
            print("✅ ASS subtitles generated successfully")
        except Exception as ass_error:
            print(f"⚠️ ASS generation failed: {ass_error}")
            # Fallback to enhanced SRT format
            create_enhanced_srt(segments, subs_path_srt, max_time=59.0)
            subs_path = subs_path_srt
            print("✅ Enhanced SRT subtitles generated as fallback")

    except Exception as e:
        print(f"⚠️ Subtitle generation failed: {e}")
        print("   📝 Error details:", str(e))
        print("   🔄 Proceeding without subtitles...")
        subs_path = None

    print("\n" + "=" * 30)
    print("STARTING SHORT VIDEO PROCESSING")
    print("=" * 30)

    return await process_video_short(audio_path, image_path, video_path, subs_path)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# 192.168.0.19

def get_ffmpeg_path():
    """Get the correct FFmpeg path based on the operating system"""
    if platform.system() == "Windows":
        # For local Windows development
        ffmpeg_path = os.path.join(os.getcwd(), "ffmpeg", "ffmpeg.exe")
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
        # Fallback to system PATH
        return "ffmpeg"
    else:
        # For Linux/Docker - use system-installed ffmpeg
        return "ffmpeg"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)

