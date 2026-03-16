import os
import shutil
import subprocess
import time
from pathlib import Path

# --- Configuration ---
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
HW_ACCEL = os.environ.get("HW_ACCEL", "true").lower() == "true"
RENDER_DEVICE = os.environ.get("RENDER_DEVICE", "renderD128")
DEVICE_PATH = f"/dev/dri/{RENDER_DEVICE}"

VIDEO_QUALITY = os.environ.get("VIDEO_QUALITY", "28")
VIDEO_CODEC = os.environ.get("VIDEO_CODEC", "hevc").lower()
VIDEO_CONTAINER = os.environ.get("VIDEO_CONTAINER", "mp4").lstrip(".")

IMAGE_FORMAT = os.environ.get("IMAGE_FORMAT", "heic").lower()
IMAGE_QUALITY = int(os.environ.get("IMAGE_QUALITY", "80"))
IMAGE_SPEED = os.environ.get("IMAGE_SPEED", "4")

EXTENSIONS_VIDEO = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.m2ts', '.mts', '.mpg', '.mpeg'}
EXTENSIONS_IMAGE = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.bmp', '.avif'}

def check_dependencies():
    tools = ['ffmpeg', 'exiftool']
    if IMAGE_FORMAT == "avif": tools.append('avifenc')
    elif IMAGE_FORMAT == "heic": tools.append('heif-enc')
    for t in tools:
        if shutil.which(t) is None:
            print(f"[FATAL] Missing tool: {t}"); exit(1)

def check_file_type(path):
    if path.suffix.lower() in EXTENSIONS_VIDEO: return "VIDEO"
    if path.suffix.lower() in EXTENSIONS_IMAGE: return "IMAGE"
    return None

def copy_with_meta(input_path, output_file):
    """Fallback for files already in the target format."""
    shutil.copy2(input_path, output_file)
    return subprocess.CompletedProcess(args=[], returncode=0)

def get_compatible_image_input(input_path, temp_path):
    """Uses ffmpeg to create a temporary PNG for picky encoders."""
    valid_native = {'.jpg', '.jpeg', '.png'}
    if input_path.suffix.lower() in valid_native:
        return input_path

    # Stage as a lossless PNG
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vframes", "1", str(temp_path)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return temp_path

# --- Processing Functions ---

def process_video_hevc_gpu(input_path, output_file):
    cmd = ["ffmpeg", "-y", "-vaapi_device", DEVICE_PATH, "-i", str(input_path),
           "-vf", "format=nv12,hwupload", "-c:v", "hevc_vaapi", "-qp", VIDEO_QUALITY,
           "-c:a", "aac", "-b:a", "192k", "-map_metadata", "0", "-movflags", "+faststart", str(output_file)]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def process_video_av1_gpu(input_path, output_file):
    cmd = ["ffmpeg", "-y", "-vaapi_device", DEVICE_PATH, "-i", str(input_path),
           "-vf", "format=nv12,hwupload", "-c:v", "av1_vaapi", "-qp", VIDEO_QUALITY,
           "-c:a", "aac", "-b:a", "192k", "-map_metadata", "0", "-movflags", "+faststart", str(output_file)]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def process_image_heic(input_path, output_file):
    if input_path.suffix.lower() == ".heic": return copy_with_meta(input_path, output_file)

    temp_png = output_file.with_suffix('.temp.png')
    safe_input = get_compatible_image_input(input_path, temp_png)

    cmd = ["heif-enc", "-q", str(IMAGE_QUALITY), str(safe_input), "-o", str(output_file)]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if temp_png.exists(): temp_png.unlink() # Clean up
    return res

def process_image_avif(input_path, output_file):
    if input_path.suffix.lower() == ".avif": return copy_with_meta(input_path, output_file)

    temp_png = output_file.with_suffix('.temp.png')
    safe_input = get_compatible_image_input(input_path, temp_png)

    qp_max = 63 - int((IMAGE_QUALITY * 63) / 100)
    cmd = ["avifenc", "--min", "0", "--max", str(qp_max), "--speed", IMAGE_SPEED, "--jobs", str(os.cpu_count()), str(safe_input), str(output_file)]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if temp_png.exists(): temp_png.unlink() # Clean up
    return res

def main():
    check_dependencies()
    print(f"--- Media Converter Started ---")
    files_to_process = [Path(root) / f for root, dirs, files in os.walk(INPUT_DIR) for f in files if check_file_type(Path(root) / f)]
    print(f"Found {len(files_to_process)} media files. Processing...")

    count = 0
    for input_path in files_to_process:
        count += 1
        try:
            rel_dir = input_path.parent.relative_to(INPUT_DIR)
            target_dir = OUTPUT_DIR / rel_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            ftype = check_file_type(input_path)

            output_file = target_dir / (f"{input_path.stem}.{VIDEO_CONTAINER if ftype == 'VIDEO' else IMAGE_FORMAT}")

            if output_file.exists() and output_file.stat().st_size > 0:
                print(f"[{count}/{len(files_to_process)}] SKIP: {input_path.name}"); continue

            start = time.time()
            if ftype == "VIDEO":
                res = process_video_av1_gpu(input_path, output_file) if VIDEO_CODEC == "av1" else process_video_hevc_gpu(input_path, output_file)
            else:
                res = process_image_avif(input_path, output_file) if IMAGE_FORMAT == "avif" else process_image_heic(input_path, output_file)
                if res.returncode == 0 and input_path.suffix.lower() not in [".heic", ".avif"]:
                    # Copy all metadata, but force Orientation to 1 (Normal) to prevent double-rotation
                    subprocess.run([
                        "exiftool",
                        "-tagsFromFile", str(input_path),
                        "-all:all",
                        "-Orientation=1", "-n",
                        "-overwrite_original",
                        str(output_file)
                    ], stdout=subprocess.DEVNULL)

            elapsed = time.time() - start

# --- Output Logging and Size Check ---
            if res.returncode == 0:
                orig_size = input_path.stat().st_size
                new_size = output_file.stat().st_size if output_file.exists() else 0

                # If the new file is larger, discard it and keep the original
                if new_size > orig_size and input_path.suffix.lower() not in [".heic", ".avif"]:
                    print(f"[{count}/{len(files_to_process)}] REVERT: {input_path.name} (Grew from {orig_size/(1024*1024):.1f}MB to {new_size/(1024*1024):.1f}MB). Keeping original.")
                    output_file.unlink() # Delete the bloated converted file
                    copy_with_meta(input_path, output_file) # Just copy the original instead
                else:
                    print(f"[{count}/{len(files_to_process)}] OK: {input_path.name} ({orig_size/(1024*1024):.1f}MB -> {new_size/(1024*1024):.1f}MB) in {elapsed:.1f}s")
            else:
                err = res.stderr.decode('utf-8', errors='ignore')[-150:].replace('\n', ' ')
                print(f"[{count}/{len(files_to_process)}] FAIL: {input_path.name} - {err}")

        except Exception as e:
            print(f"[ERROR] {input_path.name} - {str(e)}")

    print("--- Done ---")

if __name__ == "__main__":
    main()
