FROM alpine:latest

RUN apk update && apk add --no-cache \
    python3 \
    ffmpeg \
    libavif-apps \
    libheif-tools \
    exiftool \
    mesa-va-gallium \
    intel-media-driver \
    libva-intel-driver \
    libva-utils \
    bash

# Wolfi specific: symlink python so our script finds it
RUN ln -sf /usr/bin/python3 /usr/bin/python

RUN mkdir -p /data/input /data/output /app
WORKDIR /app

# Copy all scripts
COPY converter.py /app/converter.py
COPY check.py /app/check.py
COPY entrypoint.sh /app/entrypoint.sh

# Make the orchestrator executable
RUN chmod +x /app/entrypoint.sh

# The container now runs the full pipeline by default
CMD ["/app/entrypoint.sh"]
