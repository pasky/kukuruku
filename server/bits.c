#ifndef BITS_H
#define BITS_H

#include "bits.h"

#include <string.h>
#include <inttypes.h>

#if OUR_ENDIAN != TARGET_ENDIAN

void LE32(void *x) {
  uint32_t i;
  memcpy(&i, x, sizeof(i));
  i = htobe32(i);
  memcpy(x, &i, sizeof(i));
}

void LE16(void *x) {
  uint16_t i;
  memcpy(&i, x, sizeof(i));
  i = htobe16(i);
  memcpy(x, &i, sizeof(i));
}

#else

void LE32(void *x) {}
void LE16(void *x) {}

#endif

#endif
