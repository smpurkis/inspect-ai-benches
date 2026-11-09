#include "unpad.h"
#include <stdint.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    size_t block = (size_t)strtoul(argv[1], NULL, 10);
    size_t pad = (size_t)strtoul(argv[2], NULL, 10);
    size_t bad = (size_t)strtoul(argv[3], NULL, 10);
    uint8_t input[256];
    for (size_t i = 0; i < block; i++) input[i] = (uint8_t)pad;
    if (bad < block) input[bad] ^= 0x55u;
    size_t output = 0x12345678u;
    (void)pkcs7_unpad(input, block, block, &output);
    return 0;
}
