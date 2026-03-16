import os
import subprocess
import json
from pathlib import Path

# --- Configuration ---
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/output"))

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

def get_metadata(file_path):
    cmd = ["exiftool", "-j", "-DateTimeOriginal", "-GPSLatitude", "-GPSLongitude", str(file_path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            if data and len(data) > 0:
                return data[0]
        return {}
    except Exception:
        return {}

def compare_metadata(meta_src, meta_dst):
    discrepancies = []
    tags_to_check = ["DateTimeOriginal", "GPSLatitude", "GPSLongitude"]

    for tag in tags_to_check:
        val_src = meta_src.get(tag)
        val_dst = meta_dst.get(tag)
        if val_src:
            if not val_dst: discrepancies.append(f"Missing {tag}")
            elif str(val_src) != str(val_dst): discrepancies.append(f"{tag} Mismatch")

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

        # 1. Structural Check
        is_struct_ok, struct_err = check_structural_integrity(out_path)
        if not is_struct_ok:
            print(f"[FAIL] {out_path.name} -> CORRUPT FILE: {struct_err}")
            out_path.unlink() # AUTO-DELETE
            print(f"       -> Deleted corrupted file.")
            failed += 1
            continue

        # 2. Metadata Check
        is_meta_ok, meta_err = compare_metadata(get_metadata(in_path), get_metadata(out_path))
        if not is_meta_ok:
            print(f"[FAIL] {out_path.name} -> METADATA ERROR: {meta_err}")
            out_path.unlink() # AUTO-DELETE
            print(f"       -> Deleted file due to metadata mismatch.")
            failed += 1
            continue

        print(f"[OK] {out_path.name} -> Structure & Metadata Verified")
        passed += 1

    print("\n--- Integrity Check Complete ---")
    print(f"Total Verified: {passed}")
    print(f"Total Deleted:  {failed}")

if __name__ == "__main__":
    main()
