FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip \
      curl ca-certificates git build-essential xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Nim via choosenim
RUN curl -L https://nim-lang.org/choosenim/init.sh -o /tmp/choosenim.sh && \
    chmod +x /tmp/choosenim.sh && \
    CHOOSENIM_CHOOSE_VERSION=2.0.4 /tmp/choosenim.sh -y && \
    rm /tmp/choosenim.sh
ENV PATH="/root/.nimble/bin:$PATH"
RUN nim --version

RUN python3 -m pip install --no-cache-dir --break-system-packages pytest pytest-json-ctrf pytest-timeout

CMD ["bash"]
