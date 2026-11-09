#include "unpad.h"

int pkcs7_unpad(const uint8_t *input, size_t input_len,
                size_t block_size, size_t *output_len) {
    if (input == NULL || output_len == NULL || block_size == 0 ||
        block_size > 255 || input_len == 0 || input_len % block_size != 0) {
        return 0;
    }

    /* BUG: checking only p cannot detect corruption earlier in the padding. */
    uint8_t p = input[input_len - 1];
    if (p == 0 || p > block_size) {
        return 0;
    }
    *output_len = input_len - p;
    return 1;
}
