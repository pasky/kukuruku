#ifndef BITS_H
#define BITS_H

#include "bits.h"

#include <string.h>
#include <inttypes.h>

#if OUR_ENDIAN != TARGET_ENDIAN

// Convert 4 bytes to target endian
void LE32(void *x) {
  uint32_t i;
  memcpy(&i, x, sizeof(i));
  i = htole32(i);
  memcpy(x, &i, sizeof(i));
}

// Convert 2 bytes to target endian
// ofc a more efficient implementation can be imagined
void LE16(void *x) {
  uint16_t i;
  memcpy(&i, x, sizeof(i));
  i = htole16(i);
  memcpy(x, &i, sizeof(i));
}

#else

void LE32(void *x) {}
void LE16(void *x) {}

#endif

#endif
