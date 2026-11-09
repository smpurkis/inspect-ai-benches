CC ?= cc
CFLAGS := -std=c11 -O2 -Wall -Wextra -Werror -fPIC

.PHONY: all clean
all: build/libunpad.so build/pkcs7-unpad

build:
	mkdir -p build

build/libunpad.so: src/unpad.c src/unpad.h | build
	$(CC) $(CFLAGS) -shared src/unpad.c -o $@

build/pkcs7-unpad: src/unpad.c src/unpad.h src/cli.c | build
	$(CC) $(CFLAGS) src/unpad.c src/cli.c -o $@

clean:
	rm -rf build
