FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      sqlite3 \
      python3 \
      python3-pip \
      jq \
      && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-json-ctrf pytest-timeout

CMD ["bash"]
