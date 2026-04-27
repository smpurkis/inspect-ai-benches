FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      git \
      python3 \
      python3-pip \
      jq \
      curl \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

RUN git config --system user.name "Agent" && git config --system user.email "agent@example.com" && \
    python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-json-ctrf pytest-timeout

COPY repo.tgz /tmp/repo.tgz
RUN mkdir -p /app/repo && \
    tar xzf /tmp/repo.tgz -C /app/repo && \
    rm /tmp/repo.tgz && \
    git config --system --add safe.directory /app/repo

CMD ["bash"]
