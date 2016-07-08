#ifndef CLIENT_PARSER_H
#define CLIENT_PARSER_H

#include "socket.h"
#include "worker.h"
#include "sample_type.h"

int parse_client_req(tcp_cli_t *, const uint8_t *, int32_t);

enum special_payload_type {
  SPECTRUM = -1,
  HISTO = -2,
};

typedef enum command_type {
  DUMPBUFFER = 1,
  RECORD_START = 2,
  RECORD_STOP = 19,
  CREATE_XLATER = 3,
  LIST_XLATERS = 4,
  DESTROY_XLATER = 5,
  ENABLE_XLATER = 6,
  DISABLE_XLATER = 7,
  SET_GAIN = 8,
  RETUNE = 9,
  SET_PPM = 10,
  SET_HISTO_FFT = 11,
  SET_RATE = 12,
  ENABLE_SPECTRUM = 13,
  DISABLE_SPECTRUM = 14,
  ENABLE_HISTO = 15,
  DISABLE_HISTO = 16,
  GET_INFO = 17,
  MODIFY_XLATER = 18,

  PAYLOAD = 256,
  DUMPED = 257,
  RUNNING_XLATER = 258,
  INFO = 259,
  
} command_type;

typedef enum sdr_iface {
  SDR_IFACE_TUNE = 1,
  SDR_IFACE_PPM = 2,
  SDR_IFACE_GAIN = 3,
} sdr_iface;

struct __attribute__ ((__packed__)) SRV_PAYLOAD_HEADER {
  command_type t;
  int32_t id;
  int32_t time;
  int32_t frameno;
  sample_type type;
};

#endif
