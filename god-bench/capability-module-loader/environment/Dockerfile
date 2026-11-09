FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

COPY apply_patch /usr/local/bin/apply_patch

RUN apt-get update && \
    apt-get install -y --no-install-recommends git lua5.4 python3 python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    ln -s /usr/bin/lua5.4 /usr/local/bin/lua

RUN python3 -m pip install --no-cache-dir pytest pytest-timeout || \
    python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-timeout

RUN chmod +x /usr/local/bin/apply_patch
CMD ["bash"]
