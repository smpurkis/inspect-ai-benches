FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip \
      curl ca-certificates git build-essential xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Go
ENV GOVERSION=1.22.4
RUN curl -L "https://go.dev/dl/go${GOVERSION}.linux-amd64.tar.gz" -o /tmp/go.tar.gz && \
    tar -C /usr/local -xzf /tmp/go.tar.gz && \
    rm /tmp/go.tar.gz
ENV PATH="/usr/local/go/bin:$PATH"
RUN go version

RUN python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-json-ctrf pytest-timeout

CMD ["bash"]
