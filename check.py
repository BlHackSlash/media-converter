import os
import subprocess
import json
import re
from pathlib import Path

# --- Configuration ---
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
CHECKS = os.environ.get("CHECKS", "all").lower() # all, integrity, metadata, none

def check_structural_integrity(file_path):
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
    """Helper to reliably extract Latitude and Longitude into floats from either EXIF or QuickTime."""
    lat, lon = meta.get("GPSLatitude"), meta.get("GPSLongitude")

    # If standard EXIF tags exist (mostly images), use them
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except ValueError:
            pass

    # Fallback for Apple QuickTime GPSCoordinates (Lat Lon Alt)
    coords = meta.get("GPSCoordinates")
    if coords:
        # With exiftool -n, this is space-separated: e.g., "37.33 -122.03 15.4"
        parts = str(coords).split()
        if len(parts) >= 2:
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                pass

    return None, None

def get_metadata(file_path):
    # Added '-CreationDate' to catch Apple's local time tag
    cmd = ["exiftool", "-j", "-n", "-DateTimeOriginal", "-CreationDate", "-CreateDate",
           "-GPSLatitude", "-GPSLongitude", "-GPSCoordinates", "-ee", str(file_path)]
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
    """Strips timezones and extra formatting to return just YYYY:MM:DD HH:MM:SS"""
    if not date_str: return None
    match = re.search(r"(\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2})", str(date_str))
    return match.group(1) if match else None

def compare_metadata(meta_src, meta_dst):
    discrepancies = []

    # 1. Smarter Date Check
    # Grab all possible dates and strip timezones
    dates_src = {parse_base_date(meta_src.get(k)) for k in ["DateTimeOriginal", "CreationDate", "CreateDate"]}
    dates_dst = {parse_base_date(meta_dst.get(k)) for k in ["DateTimeOriginal", "CreationDate", "CreateDate"]}

    # Remove Nones from the sets
    dates_src.discard(None)
    dates_dst.discard(None)

    if dates_src:
        if not dates_dst:
            discrepancies.append("Missing Date")
        # If there is NO overlap between the source dates and destination dates, it's a mismatch
        elif not dates_src.intersection(dates_dst):
            discrepancies.append(f"Date Mismatch (Src: {dates_src} vs Dst: {dates_dst})")

    # 2. GPS Check (using the helper function from the previous fix)
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
                out_path.unlink() # AUTO-DELETE
                print(f"       -> Deleted corrupted file.")
                failed += 1
                file_failed = True
                continue # Skip to next file

        # 2. Metadata Check
        if not file_failed and CHECKS in ["all", "metadata"]:
            is_meta_ok, meta_err = compare_metadata(get_metadata(in_path), get_metadata(out_path))
            if not is_meta_ok:
                print(f"[FAIL] {out_path.name} -> METADATA ERROR: {meta_err}")
                out_path.unlink() # AUTO-DELETE
                print(f"       -> Deleted file due to metadata mismatch.")
                failed += 1
                file_failed = True
                continue # Skip to next file

        if not file_failed:
            print(f"[OK] {out_path.name} -> Verified")
            passed += 1

    print("\n--- Integrity Check Complete ---")
    print(f"Total Verified: {passed}")
    print(f"Total Deleted:  {failed}")

if __name__ == "__main__":
    main()
