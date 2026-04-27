FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

COPY apply_patch /usr/local/bin/apply_patch

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      jq \
      curl \
      ca-certificates \
      xz-utils \
      tar \
      wabt \
      \
      && rm -rf /var/lib/apt/lists/*

ARG WASM_TOOLS_URL=https://github.com/bytecodealliance/wasm-tools/releases/download/v1.245.1/wasm-tools-1.245.1-x86_64-linux.tar.gz
ARG WASMTIME_URL=https://github.com/bytecodealliance/wasmtime/releases/download/v21.0.1/wasmtime-v21.0.1-x86_64-linux.tar.xz

RUN curl -L $WASM_TOOLS_URL -o /tmp/wasm-tools.tar.gz && \
    mkdir -p /opt/wasm-tools && \
    tar -xzf /tmp/wasm-tools.tar.gz -C /opt/wasm-tools --strip-components=1 && \
    ln -s /opt/wasm-tools/wasm-tools /usr/local/bin/wasm-tools && \
    rm /tmp/wasm-tools.tar.gz

RUN curl -L $WASMTIME_URL -o /tmp/wasmtime.tar.xz && \
    mkdir -p /opt/wasmtime && \
    tar -xJf /tmp/wasmtime.tar.xz -C /opt/wasmtime --strip-components=1 && \
    ln -s /opt/wasmtime/wasmtime /usr/local/bin/wasmtime && \
    rm /tmp/wasmtime.tar.xz

RUN wasmtime --version

RUN python3 -m pip install --no-cache-dir pytest pytest-json-ctrf pytest-timeout || \
    python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-json-ctrf pytest-timeout

RUN chmod +x /usr/local/bin/apply_patch

# Record build-time hash of wat2wasm so tests can detect tampering.
RUN sha256sum /usr/bin/wat2wasm > /etc/wat2wasm.sha256

CMD ["bash"]
