FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir pytest pytest-json-ctrf pytest-timeout || \
    python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-json-ctrf pytest-timeout

CMD ["bash"]
