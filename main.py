import os
import subprocess
import re
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)


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
            response = session.get(
                download_url, stream=True, timeout=30, allow_redirects=True
            )
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")

            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            print(f"Content type: {content_type}")

            # If it's HTML, we might have a virus scan warning or other issue
            if "text/html" in content_type:
                response_text = response.text[:1000]  # First 1000 chars
                print(f"HTML Response (first 1000 chars): {response_text}")

                # Check for virus scan warning
                if (
                    "virus scan warning" in response_text.lower()
                    or "download_warning" in response_text
                ):
                    print("Detected virus scan warning, looking for bypass...")

                    # Look for download link in the page
                    import re

                    download_link_match = re.search(
                        r'href="(/uc\?export=download[^"]*)"', response_text
                    )
                    if download_link_match:
                        bypass_url = (
                            "https://drive.google.com"
                            + download_link_match.group(1).replace("&amp;", "&")
                        )
                        print(f"Found bypass URL: {bypass_url}")

                        response = session.get(bypass_url, stream=True, timeout=30)
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").lower()
                        print(f"Bypass response content type: {content_type}")

                # If still HTML, this attempt failed
                if "text/html" in content_type:
                    print(f"Attempt {attempt} failed - still getting HTML")
                    continue

            # Check if we have actual file content
            content_length = response.headers.get("content-length")
            if content_length:
                print(f"Content length: {content_length} bytes")

            # Write the file
            print(f"Writing file to: {output_path}")
            with open(output_path, "wb") as f:
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
        r"id=([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
        r"file/d/([a-zA-Z0-9_-]+)",
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

    if "drive.google.com" in url:
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

            print("File written successfully")
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
    with open(file_path, "rb") as f:
        first_bytes = f.read(500)  # Read more bytes to check
        print(f"First 50 bytes (hex): {first_bytes[:50].hex()}")
        print(f"First 200 chars: {first_bytes[:200]}")

        if b"<html" in first_bytes.lower() or b"<!doctype" in first_bytes.lower():
            print(f"ERROR: {file_type} file appears to be HTML (download failed)")
            return False

    print(f"{file_type} file verification passed")
    return True


def transcribe_audio(audio_path: str, max_duration: float = None):
    """Transcribe audio using Faster-Whisper with enhanced accuracy settings.
    
    Args:
        audio_path: Path to the audio file
        max_duration: Maximum duration to transcribe (in seconds). If None, transcribe entire file.
    """
    print("🎯 Starting audio transcription...")
    if max_duration:
        print(f"   ⏱️ Duration limit: {max_duration} seconds")
    print("📥 Loading Whisper model with enhanced accuracy settings...")
    
    # Use larger model for better accuracy
    model = WhisperModel("small", device="cpu", compute_type="int8")
    print("✅ Whisper model loaded successfully (using 'small' model for better accuracy)")
    
    print("🎵 Beginning transcription process...")
    print("   - Using word-level timestamps")
    print("   - Voice activity detection enabled")
    print("   - Enhanced accuracy settings")
    if max_duration:
        print(f"   - Limited to first {max_duration} seconds")
    
    # Prepare transcription options
    transcribe_options = {
        "word_timestamps": True,
        "vad_filter": True,
        # Enhanced accuracy settings
        "beam_size": 5,  # Increase beam size for better accuracy
        "best_of": 5,    # Generate multiple candidates and pick the best
        "temperature": 0.0,  # Use deterministic decoding for consistency
        "condition_on_previous_text": True,  # Use context from previous segments
        "compression_ratio_threshold": 2.4,  # Filter out segments with poor compression
        "log_prob_threshold": -1.0,  # Filter out low-probability segments
        "no_speech_threshold": 0.6,  # Better silence detection
        # Smaller segment length for more precise timing
        "initial_prompt": "Transcribe this audio with precise word timing."
    }
    
    # Add duration limit if specified
    if max_duration:
        transcribe_options["clip_timestamps"] = [0, max_duration]
    
    segments, info = model.transcribe(audio_path, **transcribe_options)
    
    print(f"📊 Transcription info: {info}")
    print(f"   🎤 Language detected: {info.language}")
    print(f"   📈 Language probability: {info.language_probability:.2%}")
    print("🔄 Processing transcription segments...")
    
    # Convert generator to list and validate word timestamps
    segment_list = []
    total_words = 0
    
    for segment in segments:
        # Validate and clean up word timestamps
        if hasattr(segment, 'words') and segment.words:
            cleaned_words = []
            for word in segment.words:
                # Ensure word timing is valid
                if (hasattr(word, 'start') and hasattr(word, 'end') and 
                    word.start is not None and word.end is not None and
                    word.end > word.start):
                    cleaned_words.append(word)
                    total_words += 1
            
            # Only add segment if it has valid words
            if cleaned_words:
                # Update segment with cleaned words
                segment.words = cleaned_words
                segment_list.append(segment)
    
    print(f"📝 Found {len(segment_list)} valid speech segments")
    print(f"📝 Total words with timestamps: {total_words}")
    
    return segment_list


def words_to_karaoke_ass(segments, out_path: str, max_time: float = None) -> None:
    r"""Write segments to an ASS file using \k karaoke tags with enhanced timing.
    
    Color scheme:
    - PrimaryColour (&H00FFFFFF): White for unsaid words
    - SecondaryColour (&H0087CEEB): Light blue (#87CEEB) for said words (karaoke effect)
    
    Args:
        segments: Transcription segments with word timing
        out_path: Output file path for ASS file
        max_time: Maximum time in seconds. Segments beyond this will be filtered out.
    """
    print("📝 Creating ASS subtitle file with enhanced timing...")
    if max_time:
        print(f"   ⏱️ Filtering segments beyond {max_time} seconds")
    print("🎨 Using Segoe UI (sans-serif) font with white→light blue karaoke effect")
    print("   📝 Unhighlighted words: White (#FFFFFF)")
    print("   📝 Highlighted words (being said): Light blue (#87CEEB)")
    print("   🎤 Karaoke effect: Words turn light blue as they're spoken")
    print("   📐 Bottom margin: 60px from bottom of video")
    print("   🔤 Preserving original word spacing and timing from transcription")
    print(f"📁 Output path: {out_path}")
    
    # Enhanced ASS header with sans-serif font and light blue karaoke styling
    header = """[Script Info]
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

    def format_time_precise(seconds):
        """Convert seconds to ASS time format with high precision (H:MM:SS.CC)"""
        # Round to centiseconds for ASS format precision
        centiseconds = round(seconds * 100) / 100
        hours = int(centiseconds // 3600)
        minutes = int((centiseconds % 3600) // 60)
        secs = centiseconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"

    print("✍️ Writing enhanced subtitle data with precise timing...")
    with open(out_path, "w", encoding="utf8") as fh:
        fh.write(header)
        
        # Filter segments by max_time if specified
        filtered_segments = segments
        if max_time is not None:
            filtered_segments = [seg for seg in segments if seg.start < max_time]
            print(f"   🔍 Filtered {len(segments)} → {len(filtered_segments)} segments within {max_time}s")
        
        total_segments = len(filtered_segments)
        total_words_processed = 0
        
        for i, seg in enumerate(filtered_segments, 1):
            # Use precise timing
            start_time = format_time_precise(seg.start)
            end_time = format_time_precise(seg.end)
            
            # Create karaoke text with enhanced word-level timing
            if hasattr(seg, 'words') and seg.words:
                karaoke_text = ""
                word_count = len(seg.words)
                
                # Process each word with enhanced timing
                for j, word in enumerate(seg.words):
                    # Skip words that start beyond max_time
                    if max_time is not None and word.start >= max_time:
                        continue
                    
                    # Enhanced duration calculation with minimum timing constraints
                    word_duration = word.end - word.start
                    
                    # If word extends beyond max_time, truncate it
                    if max_time is not None and word.end > max_time:
                        word_duration = max_time - word.start
                    
                    # Ensure minimum word duration (avoid too-fast highlighting)
                    min_duration = 0.1  # 100ms minimum
                    if word_duration < min_duration:
                        word_duration = min_duration
                    
                    # Convert to centiseconds and ensure it's not zero
                    duration_centis = max(1, int(word_duration * 100))
                    
                    # Preserve original word text including natural spacing - NO STRIPPING
                    word_text = word.word
                    if word_text:
                        # Add standard karaoke timing tag - will use Karaoke style colors
                        karaoke_text += f"{{\\k{duration_centis}}}{word_text}"
                        total_words_processed += 1
                
                # Only write if we have actual content
                if karaoke_text.strip():
                    fh.write(f"Dialogue: 0,{start_time},{end_time},Karaoke,,0,0,0,,{karaoke_text}\n")
            else:
                # Enhanced fallback: use segment text with even timing distribution
                segment_text = getattr(seg, 'text', '')  # Don't strip - preserve original spacing
                if segment_text:
                    # Calculate timing for each character if no word timing available
                    segment_duration = seg.end - seg.start
                    char_duration = max(5, int((segment_duration * 100) / len(segment_text)))
                    
                    karaoke_text = ""
                    for char in segment_text:
                        if char != ' ':
                            karaoke_text += f"{{\\k{char_duration}}}{char}"
                        else:
                            karaoke_text += "{\\k2} "
                    
                    fh.write(f"Dialogue: 0,{start_time},{end_time},Karaoke,,0,0,0,,{karaoke_text}\n")
            
            # Enhanced progress indicator
            if i % 5 == 0 or i == total_segments:
                print(f"   📄 Processed {i}/{total_segments} segments ({total_words_processed} words)...")
    
    print(f"✅ Enhanced ASS subtitle file created successfully!")
    print(f"   📊 Total words processed: {total_words_processed}")
    print(f"   🎯 Enhanced timing precision applied")


def create_enhanced_srt(segments, out_path: str, max_time: float = None) -> None:
    """Create an enhanced SRT subtitle file with word-level timing
    
    Args:
        segments: Transcription segments with word timing
        out_path: Output file path for SRT file
        max_time: Maximum time in seconds. Segments beyond this will be filtered out.
    """
    print("📝 Creating enhanced SRT subtitle file with improved timing...")
    if max_time:
        print(f"   ⏱️ Filtering segments beyond {max_time} seconds")
    print("🎨 SRT format: Will use sans-serif font (Segoe UI) when rendered by FFmpeg")
    print("   📐 Bottom margin: 60px (regular) / 80px (9:16) from bottom of video")
    print("   🔤 Preserving original word spacing and timing from transcription")
    print(f"📁 Output path: {out_path}")
    
    def format_srt_time_precise(seconds):
        """Convert seconds to SRT time format with millisecond precision (HH:MM:SS,mmm)"""
        # Round to milliseconds for SRT format precision
        milliseconds = round(seconds * 1000)
        total_seconds = milliseconds // 1000
        millis = milliseconds % 1000
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    with open(out_path, "w", encoding="utf8") as fh:
        subtitle_index = 1
        total_words = 0
        
        # Filter segments by max_time if specified
        filtered_segments = segments
        if max_time is not None:
            filtered_segments = [seg for seg in segments if seg.start < max_time]
            print(f"   🔍 Filtered {len(segments)} → {len(filtered_segments)} segments within {max_time}s")
        
        for seg in filtered_segments:
            # Enhanced timing for better synchronization
            if hasattr(seg, 'words') and seg.words and len(seg.words) > 1:
                # Create multiple shorter subtitle entries for better timing
                # Group words into chunks of 3-5 words for better readability
                word_chunks = []
                current_chunk = []
                
                for word in seg.words:
                    # Skip words that start beyond max_time
                    if max_time is not None and word.start >= max_time:
                        break
                    
                    current_chunk.append(word)
                    # Create chunks of 3-5 words or when there's a significant pause
                    if (len(current_chunk) >= 4 or 
                        (len(current_chunk) >= 2 and 
                         word == seg.words[-1])):  # Last word in segment
                        word_chunks.append(current_chunk)
                        current_chunk = []
                
                # Add any remaining words
                if current_chunk:
                    word_chunks.append(current_chunk)
                
                # Create subtitle entries for each chunk
                for chunk in word_chunks:
                    if not chunk:
                        continue
                        
                    start_time = format_srt_time_precise(chunk[0].start)
                    # Truncate end time if it exceeds max_time
                    chunk_end = chunk[-1].end
                    if max_time is not None and chunk_end > max_time:
                        chunk_end = max_time
                    end_time = format_srt_time_precise(chunk_end)
                    
                    # Combine words in chunk preserving original spacing
                    text_parts = []
                    for word in chunk:
                        if word.word:  # Only check if word exists, don't strip
                            text_parts.append(word.word)
                    text = "".join(text_parts)  # Join without adding spaces - preserve original
                    
                    if text:
                        fh.write(f"{subtitle_index}\n")
                        fh.write(f"{start_time} --> {end_time}\n")
                        fh.write(f"{text}\n\n")
                        subtitle_index += 1
                        total_words += len(chunk)
            else:
                # Fallback for segments without word-level timing
                start_time = format_srt_time_precise(seg.start)
                # Truncate end time if it exceeds max_time
                seg_end = seg.end
                if max_time is not None and seg_end > max_time:
                    seg_end = max_time
                end_time = format_srt_time_precise(seg_end)
                
                # Get text from segment preserving original spacing
                if hasattr(seg, 'text') and seg.text:
                    text = seg.text  # Don't strip - preserve original spacing
                elif hasattr(seg, 'words') and seg.words:
                    # Combine all words preserving original spacing
                    text_parts = []
                    for word in seg.words:
                        if word.word:  # Only check if word exists, don't strip
                            text_parts.append(word.word)
                    text = "".join(text_parts)  # Join without adding spaces - preserve original
                else:
                    continue
                
                if text:
                    fh.write(f"{subtitle_index}\n")
                    fh.write(f"{start_time} --> {end_time}\n")
                    fh.write(f"{text}\n\n")
                    subtitle_index += 1
                    total_words += len(text.split())
    
    print(f"✅ Enhanced SRT subtitle file created successfully!")
    print(f"   📊 Created {subtitle_index - 1} subtitle entries")
    print(f"   📝 Total words: {total_words}")
    print(f"   🎯 Enhanced timing with word-level precision")


async def process_video(audio_path, image_path, video_path, subs_path: str | None = None):
    """Common video processing logic - simplified without progress tracking.

    If ``subs_path`` is provided, burn the subtitles into the output.
    """
    print("🎬 Entering process_video function...")
    print(f"   📂 Working directory: {os.getcwd()}")
    
    ffmpeg_path = os.path.join(os.getcwd(), "ffmpeg", "ffmpeg.exe")
    print(f"   🔍 Looking for FFmpeg at: {ffmpeg_path}")

    # Verify ffmpeg exists
    if not os.path.exists(ffmpeg_path):
        print(f"❌ ERROR: FFmpeg not found at {ffmpeg_path}")
        raise Exception(f"FFmpeg executable not found at {ffmpeg_path}")
    
    print("✅ FFmpeg executable found")

    # FFmpeg command - optionally burn ASS subtitles
    print("🔧 Building FFmpeg command...")
    cmd = [
        ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-i",
        image_path,
        "-i",
        audio_path,
    ]

    if subs_path:
        print("📝 Adding subtitle filter to command...")
        # Convert Windows path to forward slashes and escape properly for FFmpeg
        escaped_subs_path = subs_path.replace("\\", "/")
        print(f"   🔄 Escaped subtitle path: {escaped_subs_path}")
        
        # Choose filter based on file extension
        if subs_path.endswith('.ass'):
            # Use ass filter for ASS files (supports karaoke)
            subs_filter = f"ass='{escaped_subs_path}'"
            print("   📝 Using ASS filter for karaoke effects")
        else:
            # Use subtitles filter for SRT files with sans-serif font and white color
            subs_filter = f"subtitles='{escaped_subs_path}':force_style='FontName=Segoe UI,Fontsize=48,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Bold=1,MarginV=60'"
            print("   📝 Using subtitles filter for SRT (sans-serif, white, bottom margin)")
            
        print(f"   📝 Subtitle filter: {subs_filter}")
        cmd += ["-vf", subs_filter]
    else:
        print("📝 No subtitles to add")

    cmd += [
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-pix_fmt",
        "yuv420p",
        video_path,
    ]
    
    print("✅ FFmpeg command built successfully")

    print("\n" + "=" * 30)
    print("STARTING VIDEO GENERATION")
    print("=" * 30)
    print(f"🎬 FFmpeg executable: {ffmpeg_path}")
    print(f"🎵 Audio file: {audio_path}")
    print(f"🖼️ Image file: {image_path}")
    print(f"🎥 Output file: {video_path}")
    if subs_path:
        print(f"📝 Subtitle file: {subs_path}")
    else:
        print("📝 No subtitles will be added")
    
    print(f"⚙️ Full command: {' '.join(cmd)}")

    try:
        # Use subprocess.run for simple execution
        print("🚀 Launching FFmpeg process...")
        print("   ⏳ This may take a few moments depending on audio length...")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300  # 5 minute timeout
        )
        print("🏁 FFmpeg process completed")

        if result.returncode != 0:
            print(f"FFmpeg return code: {result.returncode}")
            print("FFmpeg stdout:")
            print(result.stdout)
            print("FFmpeg stderr:")
            print(result.stderr)
            raise Exception(f"FFmpeg failed with return code {result.returncode}")

        # Verify output file
        if not os.path.exists(video_path):
            raise Exception("Output video file was not created")

        video_size = os.path.getsize(video_path)
        if video_size == 0:
            raise Exception("Output video file is empty")

        print("✅ Video generation completed successfully!")
        print(f"📁 Output file: {video_path}")
        print(f"📊 File size: {video_size:,} bytes ({video_size / 1024 / 1024:.2f} MB)")

    except subprocess.TimeoutExpired:
        print("FFmpeg process timed out after 5 minutes")
        raise Exception("Video generation timed out")
    except Exception as e:
        print(f"FFmpeg error: {e}")
        raise Exception(f"Video generation failed: {e}")

    # Return the video file
    return FileResponse(video_path, media_type="video/mp4", filename="output.mp4")


async def process_video_short(audio_path, image_path, video_path, subs_path: str | None = None):
    """Process video for 9:16 aspect ratio with 59 second limit and optional subtitles"""
    print("🎬 Entering process_video_short function...")
    print(f"   📂 Working directory: {os.getcwd()}")
    
    ffmpeg_path = os.path.join(os.getcwd(), "ffmpeg", "ffmpeg.exe")
    print(f"   🔍 Looking for FFmpeg at: {ffmpeg_path}")

    # Verify ffmpeg exists
    if not os.path.exists(ffmpeg_path):
        print(f"❌ ERROR: FFmpeg not found at {ffmpeg_path}")
        raise Exception(f"FFmpeg executable not found at {ffmpeg_path}")
    
    print("✅ FFmpeg executable found")

    # Build video filter for 9:16 aspect ratio
    print("🔧 Building FFmpeg command for 9:16 format...")
    video_filter = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    
    # Add subtitles to video filter if provided
    if subs_path:
        print("📝 Adding subtitle filter for 9:16 video...")
        escaped_subs_path = subs_path.replace("\\", "/")
        print(f"   🔄 Escaped subtitle path: {escaped_subs_path}")
        
        # Choose filter based on file extension
        if subs_path.endswith('.ass'):
            # Use ass filter for ASS files (supports karaoke)
            subs_filter = f"ass='{escaped_subs_path}'"
            print("   📝 Using ASS filter for karaoke effects")
        else:
            # Use subtitles filter for SRT files with larger font for vertical video
            subs_filter = f"subtitles='{escaped_subs_path}':force_style='FontName=Segoe UI,Fontsize=72,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Bold=1,MarginV=80'"
            print("   📝 Using subtitles filter for SRT (9:16 optimized, sans-serif, white, bottom margin)")
            
        video_filter = f"{video_filter},{subs_filter}"
        print(f"   📝 Combined video filter: {video_filter}")
    else:
        print("📝 No subtitles to add")

    # FFmpeg command for 9:16 vertical video, 59 seconds max
    cmd = [
        ffmpeg_path,
        "-y",  # Overwrite output files
        "-loop",
        "1",
        "-i",
        image_path,
        "-i",
        audio_path,
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        "59",  # Limit duration to 59 seconds
        "-vf",
        video_filter,  # Use the combined video filter
        "-pix_fmt",
        "yuv420p",
        video_path,
    ]
    
    print("✅ FFmpeg command built successfully")

    print("\n" + "=" * 30)
    print("STARTING SHORT VIDEO GENERATION (9:16, 59s)")
    print("=" * 30)
    print(f"🎬 FFmpeg executable: {ffmpeg_path}")
    print(f"🎵 Audio file: {audio_path}")
    print(f"🖼️ Image file: {image_path}")
    print(f"🎥 Output file: {video_path}")
    if subs_path:
        print(f"📝 Subtitle file: {subs_path}")
    else:
        print("📝 No subtitles will be added")
    print("📺 Format: 9:16 aspect ratio, max 59 seconds")
    
    print(f"⚙️ Full command: {' '.join(cmd)}")

    try:
        # Use subprocess.run for simple execution
        print("🚀 Launching FFmpeg process for short video...")
        print("   ⏳ This may take a few moments depending on audio length...")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300  # 5 minute timeout
        )
        print("🏁 FFmpeg process completed")

        if result.returncode != 0:
            print(f"FFmpeg return code: {result.returncode}")
            print("FFmpeg stdout:")
            print(result.stdout)
            print("FFmpeg stderr:")
            print(result.stderr)
            raise Exception(f"FFmpeg failed with return code {result.returncode}")

        # Verify output file
        if not os.path.exists(video_path):
            raise Exception("Output video file was not created")

        video_size = os.path.getsize(video_path)
        if video_size == 0:
            raise Exception("Output video file is empty")

        print("✅ Short video generation completed successfully!")
        print(f"📁 Output file: {video_path}")
        print(f"📊 File size: {video_size:,} bytes ({video_size / 1024 / 1024:.2f} MB)")
        print("📺 Format: 9:16 aspect ratio, max 59 seconds")

    except subprocess.TimeoutExpired:
        print("FFmpeg process timed out after 5 minutes")
        raise Exception("Video generation timed out")
    except Exception as e:
        print(f"FFmpeg error: {e}")
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
    
    return await process_video(audio_path, image_path, video_path)  #, subs_path)


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
    if not (audio_url.startswith("http://") or audio_url.startswith("https://")):
        raise Exception("Audio URL must start with http:// or https://")

    if not (image_url.startswith("http://") or image_url.startswith("https://")):
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

    # Transcribe and build subtitles for short video
    print("\n" + "=" * 30)
    print("GENERATING SUBTITLES FOR SHORT VIDEO")
    print("=" * 30)
    subs_path = None
    try:
        print("🎯 Step 1: Transcribing audio (limited to 59 seconds)...")
        segments = transcribe_audio(audio_path, max_duration=59.0)
        
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
