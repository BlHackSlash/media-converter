FROM alpine:latest

# We pass this variable from GitHub Actions. Default is 'cpu'.
ARG HW_TYPE=cpu

# 1. Install Base Dependencies (Every hardware type gets these)
RUN apk update && apk add --no-cache \
    python3 \
    ffmpeg \
    libavif-apps \
    libheif-tools \
    exiftool \
    bash

# 2. Install Hardware-Specific Drivers
RUN if [ "$HW_TYPE" = "intel" ]; then \
        apk add --no-cache intel-media-driver libva-intel-driver libva-utils; \
    elif [ "$HW_TYPE" = "amd" ]; then \
        apk add --no-cache mesa-va-gallium libva-utils; \
    elif [ "$HW_TYPE" = "latest" ]; then \
        # 'latest' installs everything for universal hardware support
        apk add --no-cache intel-media-driver libva-intel-driver mesa-va-gallium libva-utils; \
    fi

# 3. Setup Python and Directories
RUN ln -sf /usr/bin/python3 /usr/bin/python
RUN mkdir -p /data/input /data/output /app
WORKDIR /app

# 4. Copy Scripts
COPY converter.py /app/converter.py
COPY check.py /app/check.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
