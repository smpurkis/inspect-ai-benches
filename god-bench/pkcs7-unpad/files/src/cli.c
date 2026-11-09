#include "unpad.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: pkcs7-unpad BLOCK_SIZE HEX\n");
        return 2;
    }
    char *end = NULL;
    errno = 0;
    unsigned long block = strtoul(argv[1], &end, 10);
    size_t hex_len = 0;
    while (argv[2][hex_len] != '\0') hex_len++;
    if (errno || *end != '\0' || (hex_len & 1u)) return 2;
    size_t len = hex_len / 2;
    uint8_t *data = malloc(len ? len : 1);
    if (data == NULL) return 2;
    for (size_t i = 0; i < len; i++) {
        unsigned value;
        if (sscanf(argv[2] + 2 * i, "%2x", &value) != 1) {
            free(data);
            return 2;
        }
        data[i] = (uint8_t)value;
    }
    size_t output_len = 0x5a5a5a5au;
    int ok = pkcs7_unpad(data, len, (size_t)block, &output_len);
    if (ok) printf("ok %zu\n", output_len);
    else printf("invalid\n");
    free(data);
    return ok ? 0 : 1;
}
