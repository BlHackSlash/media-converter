### **Media Processing Pipeline: Convert & Verify**

An automated containerized pipeline designed to intelligently convert your entire image and video library into modern, space-efficient formats (HEIC, AVIF, HEVC, AV1) while preserving critical metadata and ensuring file integrity. The process leverages GPU hardware acceleration for maximum performance and includes a robust verification step.

This solution is perfect for optimizing large media archives without losing history or quality. The pipeline recursively scans your input directory, processes media files into a mirrored directory structure, and automatically deletes any corrupted or metadata-mismatched files from the output.
####
**Images on Docker Hub**: <https://hub.docker.com/r/blhackslash/media-converter>

#### **Key Features**

* **Intelligent Conversion:** Converts diverse media formats to efficient alternatives.
    * **Video:** Converts to HEVC (`x265`) or AV1 within an MP4 container.
    * **Images:** Converts to HEIC or AVIF.
* **Recursive Processing:** Scans nested folders in the input and replicates the structure in the output.
* **Hardware Acceleration (GPU):** Full support for VAAPI-based hardware acceleration on both Intel and AMD GPUs for video encoding.
* **Metadata Preservation:** Uses `exiftool` to copy critical metadata (like Creation Date, GPS coordinates) from source to converted file. It also intelligently resets image orientation to prevent double-rotation issues.
* **Automated Verification:** A post-processing script runs integrity checks on all generated files.
    * **Structural Check:** Uses `ffprobe` to ensure files are not corrupt.
    * **Metadata Mismatch Check:** Verifies key metadata tags match the source file.
    * **Auto-Deletion:** Corrupted or invalid files are immediately deleted from the output to maintain archive quality.
* **Smart "Revert" Logic:** If a converted image is larger than its original counterpart, the pipeline deletes the larger file and just copies the original, unless the original was already in a modern format.

---

### **Supported Tags**

Choose the image tag that matches your hardware for optimal performance.

| Tag | Description | Use Case |
| :--- | :--- | :--- |
| **`latest`** | Default image. Supports hardware acceleration on **both Intel and AMD** GPUs. | General purpose. Recommended for mixed environments or if unsure. |
| **`intel`** | Optimized specifically for **Intel** QuickSync Video (VAAPI) hardware acceleration. | Use on machines with an Intel CPU with integrated graphics or an Intel discrete GPU. |
| **`amd`** | Optimized specifically for **AMD** Radeon (VAAPI) hardware acceleration. | Use on machines with an AMD CPU with integrated graphics or an AMD discrete GPU. |
| **`cpu`** | Minimal image without GPU drivers. | Use on machines without a supported GPU. Can be resource heavy. |
---

### **Quick Start: Docker Compose**

The most common way to run the pipeline is via Docker Compose. This example sets up the service to process media with hardware acceleration and standard quality settings.

```yaml
services:
  media-pipeline:
    image: blhackslash/media-converter:latest  # Or choose :intel, :amd
    container_name: media-converter
    devices:
      - /dev/dri:/dev/dri  # Pass the GPU device for acceleration
    volumes:
      - /path/to/your/photos/source:/data/input  # Recursive source folder
      - /path/to/your/processed/photos:/data/output # Recursive destination folder
    environment:
      - HW_ACCEL=true             # Enable hardware acceleration (default)
      - VIDEO_CODEC=hevc           # Set default video codec (hevc or av1)
      - VIDEO_QUALITY=32          # Integer quality level (lower is better, default 28)
      - IMAGE_FORMAT=heic         # Set default image format (heic or avif)
      - IMAGE_QUALITY=60          # Integer image quality (0-100, default 80)
    # The pipeline runs once and then exits. Set a restart policy if you want it to trigger again on changes.
    # restart: unless-stopped
```

---

### **Environment Variables**

You can customize the conversion process by setting the following environment variables.

| Variable Name | Available Options | Default | Description |
| :--- | :--- | :--- | :--- |
| **`HW_ACCEL`** | `true`, `false` | `true` | Enables or disables VAAPI hardware acceleration for video encoding. Falls back to CPU encoders (`libx265`/`libsvtav1`) if `false`. |
| **`RENDER_DEVICE`** | `renderD128`, `renderD129`, etc. | `renderD128` | Specifies the render node to use for hardware acceleration. Found in `/dev/dri/`. |
| **`VIDEO_CODEC`** | `hevc`, `av1` | `hevc` | Defines the codec used for video files. |
| **`VIDEO_QUALITY`** | Integer (CRF/QP) | **`32`** | Sets the target quality for video encoding. Lower is higher quality. Range is codec dependent. |
| **`VIDEO_PRESET`** | `slow`, `medium`, `fast`, `0`-`13` | *Auto* | Encoding speed/efficiency. Defaults to **`medium`** (HEVC) or **`6`** (AV1) if not specified. |
| **`VIDEO_CONTAINER`** | `mp4`, `mkv`, etc. | `mp4` | The file extension for all output videos. |
| **`IMAGE_FORMAT`** | `heic`, `avif` | `heic` | Defines the modern format for image files. |
| **`IMAGE_QUALITY`** | Integer `0` - `100` | **`60`** | Sets the target quality for image encoding. |
| **`IMAGE_SPEED`** | Integer `0` - `9` | `4` | Controls the encoding speed for AVIF files (`avifenc`). |
| **`CHECKS`** | `all`, `integrity`, `metadata`, `none` | `all` | Controls which validation steps run after conversion. |
| **`FORCE_OVERWRITE`** | `true`, `false` | `false` | If `true`, re-processes and overwrites files already present in the output directory. |
| **`LIMIT_SIZE`** | `always`, `videos`, `images`, `never` | `always` | If the converted file is larger than the original, it reverts and keeps the original file. |
| **`INPUT_DIR`** | Path | `/data/input` | The directory containing your source files. |
| **`OUTPUT_DIR`** | Path | `/data/output` | The directory where processed files are stored. |
