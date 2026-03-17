FROM alpine:latest

# Update and install dependencies
RUN apk update && apk add --no-cache \
    python3 \
    ffmpeg \
    libavif-apps \
    libheif-tools \
    exiftool \
    # GPU Drivers
    mesa-va-gallium \
    intel-media-driver \
    libva-intel-driver \
    libva-utils \
    bash

# Ensure a virtual environment isn't strictly required for simple scripts
# and symlink python for convenience
RUN ln -sf /usr/bin/python3 /usr/bin/python

RUN mkdir -p /data/input /data/output /app
WORKDIR /app

# Copy all scripts
COPY converter.py /app/converter.py
COPY check.py /app/check.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
