#ifndef SDR_PACKET_H
#define SDR_PACKET_H

#include <inttypes.h>

// One packet that we read from SDR

typedef struct sdr_packet {
  int64_t frequency;
  int timestamp;
  int32_t frameno;
  float * data;     // the actual data, SDRPACKET complex samples
  float * spectrum; // spectrum computed with calc_spectrum
  size_t spectrumsize; // size of spectrum (bytes)
  uint16_t * histo; // histogram computed by calc_histogram
} sdr_packet;

#endif
