FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      e2fsprogs \
      fuse3 \
      golang-go \
      python3 \
      python3-pip \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pytest pytest-json-ctrf pytest-timeout

COPY create_disk_image.py /tmp/create_disk_image.py
RUN python3 /tmp/create_disk_image.py && rm /tmp/create_disk_image.py

CMD ["bash"]
