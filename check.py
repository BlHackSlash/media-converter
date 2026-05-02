import os
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime

# --- Configuration ---
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
CHECKS = os.environ.get("CHECKS", "all").lower() 

# Added Variables for Robustness
MODE = os.environ.get("MODE", "full").lower() # convert, check, full
DATE_TOLERANCE_SECONDS = int(os.environ.get("DATE_TOLERANCE_SECONDS", 86400)) # Default 24h for timezone drift
DURATION_TOLERANCE_SECONDS = float(os.environ.get("DURATION_TOLERANCE_SECONDS", 5.0)) # 5 second leniency

def check_structural_integrity(file_path):
    # Check 1: Is the file completely empty?
    if file_path.stat().st_size == 0:
        return False, "File is 0 bytes."

    # Check 2: FFprobe container scan
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and not res.stderr.strip():
            return True, ""
        return False, res.stderr.strip().replace('\n', ' ')[:100]
    except Exception as e:
        return False, str(e)

def extract_gps(meta):
    lat, lon = meta.get("GPSLatitude"), meta.get("GPSLongitude")

    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except ValueError:
            pass

    coords = meta.get("GPSCoordinates")
    if coords:
        parts = str(coords).split()
        if len(parts) >= 2:
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                pass

    return None, None

def get_metadata(file_path):
    # Added -Duration to track if the converted file was truncated
    cmd = ["exiftool", "-j", "-n", "-DateTimeOriginal", "-CreationDate", "-CreateDate",
           "-GPSLatitude", "-GPSLongitude", "-GPSCoordinates", "-Duration", "-ee", str(file_path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            if data and len(data) > 0:
                return data[0]
        return {}
    except Exception:
        return {}

def parse_base_date(date_str):
    if not date_str: return None
    match = re.search(r"(\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2})", str(date_str))
    if match:
        try:
            # Convert to actual datetime object for math
            return datetime.strptime(match.group(1), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    return None

def compare_metadata(meta_src, meta_dst):
    discrepancies = []

    # 1. Date Comparison with Tolerance
    dates_src = [parse_base_date(meta_src.get(k)) for k in ["DateTimeOriginal", "CreationDate", "CreateDate"]]
    dates_dst = [parse_base_date(meta_dst.get(k)) for k in ["DateTimeOriginal", "CreationDate", "CreateDate"]]

    # Filter out None values
    dates_src = [d for d in dates_src if d]
    dates_dst = [d for d in dates_dst if d]

    if dates_src:
        if not dates_dst:
            discrepancies.append("Missing Date")
        else:
            # Look for ANY valid match within the tolerance window
            match_found = False
            for d_src in dates_src:
                for d_dst in dates_dst:
                    if abs((d_src - d_dst).total_seconds()) <= DATE_TOLERANCE_SECONDS:
                        match_found = True
                        break
                if match_found: break
            
            if not match_found:
                discrepancies.append(f"Date Mismatch (exceeded {DATE_TOLERANCE_SECONDS}s tolerance)")

    # 2. GPS Comparison
    lat_src, lon_src = extract_gps(meta_src)
    lat_dst, lon_dst = extract_gps(meta_dst)

    if lat_src is not None and lon_src is not None:
        if lat_dst is None or lon_dst is None:
            discrepancies.append("Missing GPS Data")
        else:
            if abs(lat_src - lat_dst) > 0.0001:
                discrepancies.append("Latitude Mismatch")
            if abs(lon_src - lon_dst) > 0.0001:
                discrepancies.append("Longitude Mismatch")

    # 3. Duration Comparison (Ensures the file wasn't truncated)
    dur_src = meta_src.get("Duration")
    dur_dst = meta_dst.get("Duration")
    if dur_src is not None and dur_dst is not None:
        try:
            if abs(float(dur_src) - float(dur_dst)) > DURATION_TOLERANCE_SECONDS:
                discrepancies.append("Duration Mismatch (File may be truncated)")
        except ValueError:
            pass

    if not discrepancies: return True, ""
    return False, " | ".join(discrepancies)

def get_input_files():
    input_files = {}
    for root, dirs, files in os.walk(INPUT_DIR):
        for f in files:
            path = Path(root) / f
            rel_dir = path.parent.relative_to(INPUT_DIR)
            input_files[(str(rel_dir), path.stem)] = path
    return input_files

def main():
    if MODE == "convert":
        print("--- Integrity Check Skipped (MODE=convert) ---")
        return

    print("--- Starting Integrity Check ---")

    if CHECKS == "none":
        print("Checks disabled by environment variable (CHECKS=none). Exiting gracefully.")
        return

    if not OUTPUT_DIR.exists() or not INPUT_DIR.exists():
        print("[ERROR] Input or Output directory missing.")
        return

    input_map = get_input_files()
    output_files = [Path(root) / f for root, dirs, files in os.walk(OUTPUT_DIR) for f in files]

    print(f"Found {len(output_files)} files in output directory to verify...\n")
    passed = 0; failed = 0

    for out_path in output_files:
        rel_dir = str(out_path.parent.relative_to(OUTPUT_DIR))
        in_path = input_map.get((rel_dir, out_path.stem))

        if not in_path:
            print(f"[WARN] No matching input file found for: {out_path.name}")
            continue

        file_failed = False

        # 1. Structural Check
        if CHECKS in ["all", "integrity"]:
            is_struct_ok, struct_err = check_structural_integrity(out_path)
            if not is_struct_ok:
                print(f"[FAIL] {out_path.name} -> CORRUPT FILE: {struct_err}")
                out_path.unlink() 
                print(f"       -> Deleted corrupted file.")
                failed += 1
                file_failed = True
                continue 

        # 2. Metadata Check & Fix
        if not file_failed and CHECKS in ["all", "metadata"]:
            is_meta_ok, meta_err = compare_metadata(get_metadata(in_path), get_metadata(out_path))
            if not is_meta_ok:
                print(f"[WARN] {out_path.name} -> METADATA ERROR: {meta_err}. Attempting fix...")
                
                # Try to re-apply the EXIF fix directly over the file
                subprocess.run([
                    "exiftool", "-tagsFromFile", str(in_path),
                    "-all:all",                                
                    "-Orientation<Rotation",                  
                    "-Orientation<Orientation",                
                    "-overwrite_original", str(out_path)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # Re-verify after fix
                is_meta_ok_retry, meta_err_retry = compare_metadata(get_metadata(in_path), get_metadata(out_path))
                
                if not is_meta_ok_retry:
                    print(f"[FAIL] {out_path.name} -> FIX FAILED: {meta_err_retry}")
                    out_path.unlink() 
                    print(f"       -> Deleted file due to unrecoverable metadata.")
                    failed += 1
                    file_failed = True
                    continue
                else:
                    print(f"       -> Metadata restored successfully!")

        if not file_failed:
            print(f"[OK] {out_path.name} -> Verified")
            passed += 1

    print("\n--- Integrity Check Complete ---")
    print(f"Total Verified: {passed}")
    print(f"Total Deleted:  {failed}")

if __name__ == "__main__":
    main()
