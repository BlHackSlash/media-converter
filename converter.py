import os
import shutil
import subprocess
import time
import concurrent.futures
from pathlib import Path

# --- Configuration ---
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
HW_ACCEL = os.environ.get("HW_ACCEL", "true").lower() == "true"
RENDER_DEVICE = os.environ.get("RENDER_DEVICE", "renderD128")
DEVICE_PATH = f"/dev/dri/{RENDER_DEVICE}"

# Added Mode Variable
MODE = os.environ.get("MODE", "full").lower() # convert, check, full

# Explicit Multi-threading Configuration
JOBS = int(os.environ.get("JOBS", "4"))       # Number of files processed simultaneously
THREADS = str(os.environ.get("THREADS", "2")) # CPU threads allocated per encoder instance

# Quality Defaults Updated
VIDEO_QUALITY = os.environ.get("VIDEO_QUALITY", "28")
VIDEO_CODEC = os.environ.get("VIDEO_CODEC", "hevc").lower()
VIDEO_CONTAINER = os.environ.get("VIDEO_CONTAINER", "mp4").lstrip(".")
VIDEO_PRESET = os.environ.get("VIDEO_PRESET")

IMAGE_FORMAT = os.environ.get("IMAGE_FORMAT", "heic").lower()
IMAGE_QUALITY = int(os.environ.get("IMAGE_QUALITY", "60"))
IMAGE_SPEED = os.environ.get("IMAGE_SPEED", "4")

# New Features
FORCE_OVERWRITE = os.environ.get("FORCE_OVERWRITE", "false").lower() == "true"
LIMIT_SIZE = os.environ.get("LIMIT_SIZE", "always").lower() # always, videos, images, never

EXTENSIONS_VIDEO = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.m2ts', '.mts', '.mpg', '.mpeg'}
EXTENSIONS_IMAGE = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.bmp', '.avif'}

def get_default_preset(codec):
    if VIDEO_PRESET:
        return VIDEO_PRESET
    return "6" if codec == "av1" else "medium"

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
    shutil.copy2(input_path, output_file)
    return subprocess.CompletedProcess(args=[], returncode=0)

def get_compatible_image_input(input_path, temp_path):
    valid_native = {'.jpg', '.jpeg', '.png'}
    if input_path.suffix.lower() in valid_native:
        return input_path

    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vframes", "1", str(temp_path)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return temp_path

# --- Processing Functions ---
def process_video_hevc_gpu(input_path, output_file):
    cmd = [
        "ffmpeg", "-y", "-threads", THREADS, "-vaapi_device", DEVICE_PATH, "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a?",              
        "-map_metadata", "0",                          
        "-map_metadata:s:v", "0:s:v",                  
        "-map_chapters", "0",                          
        "-vf", "format=nv12,hwupload",                
        "-c:v", "hevc_vaapi", "-qp", VIDEO_QUALITY,
        "-metadata:s:v:0", "rotate=",                  
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",                    
        "-movflags", "+use_metadata_tags",
        str(output_file)
    ]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def process_video_av1_gpu(input_path, output_file):
    cmd = [
        "ffmpeg", "-y", "-threads", THREADS, "-vaapi_device", DEVICE_PATH, "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a?",
        "-map_metadata", "0",
        "-map_metadata:s:v", "0:s:v",
        "-map_chapters", "0",
        "-vf", "format=nv12,hwupload",
        "-c:v", "av1_vaapi", "-qp", VIDEO_QUALITY,
        "-metadata:s:v:0", "rotate=",                 
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-movflags", "+use_metadata_tags",
        str(output_file)
    ]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def process_video_hevc_cpu(input_path, output_file):
    preset = get_default_preset("hevc")
    cmd = [
        "ffmpeg", "-y", "-threads", THREADS, "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a?",
        "-map_metadata", "0",
        "-map_metadata:s:v", "0:s:v",
        "-map_chapters", "0",
        "-c:v", "libx265", "-crf", VIDEO_QUALITY, "-preset", preset,
        "-metadata:s:v:0", "rotate=",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-movflags", "+use_metadata_tags",
        str(output_file)
    ]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def process_video_av1_cpu(input_path, output_file):
    preset = get_default_preset("av1")
    cmd = [
        "ffmpeg", "-y", "-threads", THREADS, "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a?",
        "-map_metadata", "0",
        "-map_metadata:s:v", "0:s:v",
        "-map_chapters", "0",
        "-c:v", "libsvtav1", "-crf", VIDEO_QUALITY, "-preset", preset,
        "-metadata:s:v:0", "rotate=",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-movflags", "+use_metadata_tags",
        str(output_file)
    ]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def process_image_heic(input_path, output_file):
    if input_path.suffix.lower() == ".heic": return copy_with_meta(input_path, output_file)

    temp_png = output_file.with_suffix('.temp.png')
    safe_input = get_compatible_image_input(input_path, temp_png)

    cmd = ["heif-enc", "-q", str(IMAGE_QUALITY), str(safe_input), "-o", str(output_file)]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if temp_png.exists(): temp_png.unlink()
    return res

def process_image_avif(input_path, output_file):
    if input_path.suffix.lower() == ".avif": return copy_with_meta(input_path, output_file)

    temp_png = output_file.with_suffix('.temp.png')
    safe_input = get_compatible_image_input(input_path, temp_png)

    qp_max = 63 - int((IMAGE_QUALITY * 63) / 100)

    # Use the explicit THREADS variable instead of dynamically calculating
    cmd = ["avifenc", "--min", "0", "--max", str(qp_max), "--speed", IMAGE_SPEED, "--jobs", THREADS, str(safe_input), str(output_file)]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if temp_png.exists(): temp_png.unlink()
    return res

def process_single_file(input_path):
    """Worker function for processing a single file"""
    try:
        rel_dir = input_path.parent.relative_to(INPUT_DIR)
        target_dir = OUTPUT_DIR / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        ftype = check_file_type(input_path)

        output_file = target_dir / (f"{input_path.stem}.{VIDEO_CONTAINER if ftype == 'VIDEO' else IMAGE_FORMAT}")

        if not FORCE_OVERWRITE and output_file.exists() and output_file.stat().st_size > 0:
            return {"status": "SKIP", "file": input_path.name, "orig_size": 0, "new_size": 0, "msg": ""}

        start = time.time()
        if ftype == "VIDEO":
            if HW_ACCEL:
                res = process_video_av1_gpu(input_path, output_file) if VIDEO_CODEC == "av1" else process_video_hevc_gpu(input_path, output_file)
            else:
                res = process_video_av1_cpu(input_path, output_file) if VIDEO_CODEC == "av1" else process_video_hevc_cpu(input_path, output_file)
        else:
            res = process_image_avif(input_path, output_file) if IMAGE_FORMAT == "avif" else process_image_heic(input_path, output_file)
        
        if res.returncode == 0 and input_path.suffix.lower() not in [".heic", ".avif"]:
            subprocess.run([
                "exiftool", "-tagsFromFile", str(input_path),
                "-all:all",                               
                "-Orientation<Rotation",                  
                "-Orientation<Orientation",               
                "-overwrite_original", str(output_file)
            ], stdout=subprocess.DEVNULL)

        elapsed = time.time() - start

        if res.returncode == 0:
            orig_size = input_path.stat().st_size
            new_size = output_file.stat().st_size if output_file.exists() else 0

            should_limit = False
            if LIMIT_SIZE == "always": should_limit = True
            elif LIMIT_SIZE == "videos" and ftype == "VIDEO": should_limit = True
            elif LIMIT_SIZE == "images" and ftype == "IMAGE": should_limit = True

            if should_limit and new_size > orig_size and input_path.suffix.lower() not in [".heic", ".avif"]:
                output_file.unlink()
                copy_with_meta(input_path, output_file)
                new_size = orig_size
                msg = f"(Grew from {orig_size/(1024*1024):.1f}MB to {new_size/(1024*1024):.1f}MB). Keeping original."
                return {"status": "REVERT", "file": input_path.name, "orig_size": orig_size, "new_size": new_size, "msg": msg}
            else:
                msg = f"({orig_size/(1024*1024):.1f}MB -> {new_size/(1024*1024):.1f}MB) in {elapsed:.1f}s"
                return {"status": "OK", "file": input_path.name, "orig_size": orig_size, "new_size": new_size, "msg": msg}
        else:
            err = res.stderr.decode('utf-8', errors='ignore')[-250:].replace('\n', ' ')
            return {"status": "FAIL", "file": input_path.name, "orig_size": 0, "new_size": 0, "msg": err}

    except Exception as e:
        return {"status": "ERROR", "file": input_path.name, "orig_size": 0, "new_size": 0, "msg": str(e)}

def main():
    if MODE == "check":
        print("--- Media Converter Skipped (MODE=check) ---")
        return

    check_dependencies()
    print(f"--- Media Converter Started ({JOBS} Concurrent Jobs | {THREADS} Threads per Job) ---")
    files_to_process = [Path(root) / f for root, dirs, files in os.walk(INPUT_DIR) for f in files if check_file_type(Path(root) / f)]
    total_files = len(files_to_process)
    print(f"Found {total_files} media files. Processing...")

    total_orig_size = 0
    total_new_size = 0
    count = 0

    # Execute processing using ProcessPoolExecutor with JOBS variable
    with concurrent.futures.ProcessPoolExecutor(max_workers=JOBS) as executor:
        future_to_file = {executor.submit(process_single_file, fp): fp for fp in files_to_process}

        for future in concurrent.futures.as_completed(future_to_file):
            count += 1
            res = future.result()
            
            status = res["status"]
            fname = res["file"]
            msg = res["msg"]

            if status in ["OK", "REVERT"]:
                total_orig_size += res["orig_size"]
                total_new_size += res["new_size"]

            if status == "SKIP":
                print(f"[{count}/{total_files}] SKIP: {fname}")
            elif status in ["OK", "REVERT"]:
                print(f"[{count}/{total_files}] {status}: {fname} {msg}")
            else:
                print(f"[{count}/{total_files}] {status}: {fname} - {msg}")

    print("\n--- Pipeline Summary ---")
    saved = total_orig_size - total_new_size
    print(f"Original Size: {total_orig_size/(1024*1024*1024):.2f} GB")
    print(f"Converted Size: {total_new_size/(1024*1024*1024):.2f} GB")
    print(f"Total Storage Saved: {saved/(1024*1024):.1f} MB ({(saved/total_orig_size*100) if total_orig_size > 0 else 0:.1f}%)")
    print("--- Done ---")

if __name__ == "__main__":
    main()
