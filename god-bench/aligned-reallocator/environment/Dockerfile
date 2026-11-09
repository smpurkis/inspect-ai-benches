FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip curl xz-utils ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

RUN curl -L https://ziglang.org/download/0.13.0/zig-linux-x86_64-0.13.0.tar.xz -o /tmp/zig.tar.xz && \
    mkdir -p /opt/zig && tar -xJf /tmp/zig.tar.xz -C /opt/zig --strip-components=1 && \
    ln -s /opt/zig/zig /usr/local/bin/zig && rm /tmp/zig.tar.xz && zig version

RUN python3 -m pip install --break-system-packages --no-cache-dir \
      pytest==8.4.1 pytest-timeout pytest-json-ctrf==0.3.5

COPY apply_patch /usr/local/bin/apply_patch
RUN chmod +x /usr/local/bin/apply_patch
CMD ["bash"]
