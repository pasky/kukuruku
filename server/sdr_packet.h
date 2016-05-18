#ifndef SDR_PACKET_H
#define SDR_PACKET_H

#include <inttypes.h>
typedef struct sdr_packet {
  int64_t frequency;
  int timestamp;
  int32_t frameno;
  float * data;
  float * spectrum;
  size_t spectrumsize;
  uint16_t * histo;
} sdr_packet;

#endif
