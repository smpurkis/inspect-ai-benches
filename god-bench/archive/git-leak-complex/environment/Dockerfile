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
    python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-json-ctrf pytest-timeout git-filter-repo

COPY repo_small.tgz /tmp/repo_small.tgz
COPY repo_large.tgz /tmp/repo_large.tgz
RUN mkdir -p /app/repo /app/repo_large && \
    tar xzf /tmp/repo_small.tgz -C /app/repo && \
    tar xzf /tmp/repo_large.tgz -C /app/repo_large && \
    rm /tmp/repo_small.tgz /tmp/repo_large.tgz && \
    git config --system --add safe.directory /app/repo && \
    git config --system --add safe.directory /app/repo_large

CMD ["bash"]
