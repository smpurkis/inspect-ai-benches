#ifndef PKCS7_UNPAD_H
#define PKCS7_UNPAD_H

#include <stddef.h>
#include <stdint.h>

int pkcs7_unpad(const uint8_t *input, size_t input_len,
                size_t block_size, size_t *output_len);

#endif
