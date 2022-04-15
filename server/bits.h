#ifndef BITS_H
#define BITS_H

#include <machine/endian.h>

#define OUR_ENDIAN __BYTE_ORDER
#define TARGET_ENDIAN __LITTLE_ENDIAN

void LE32(void *x);
void LE16(void *x);

#endif
