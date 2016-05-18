#include "socket.h"
#include "worker.h"
#include "sample_type.h"

int parse_client_req(tcp_cli_t *, char *, int32_t);

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


struct __attribute__ ((__packed__)) CLI_CREATE_XLATER {
  int32_t remoteid;
  float rotate;
  int32_t decimation;
  int32_t startframe;
};

struct __attribute__ ((__packed__)) CLI_ENABLE_XLATER {
  int32_t id;
  sample_type type;
};

struct __attribute__ ((__packed__)) CLI_DISABLE_XLATER {
  int32_t id;
};

struct __attribute__ ((__packed__)) CLI_MODIFY_XLATER {
  int32_t localid;
  float rotate;
  int32_t newtaps;
};

struct __attribute__ ((__packed__)) CLI_DESTROY_XLATER {
  int32_t id;
};

struct __attribute__ ((__packed__)) CLI_RECORD_START {
  int32_t startframe;
  int32_t stopframe;
};

struct __attribute__ ((__packed__)) CLI_SET_GAIN {
  int32_t autogain;
  int32_t global_gain;
  int32_t if_gain;
  int32_t bb_gain;
};

struct __attribute__ ((__packed__)) CLI_RETUNE {
  int64_t freq;
};

struct __attribute__ ((__packed__)) CLI_SET_PPM {
  int32_t ppm;
};

struct __attribute__ ((__packed__)) CLI_SET_HISTO_FFT {
  int32_t fftsize;
  int32_t decim;
};

struct __attribute__ ((__packed__)) SRV_RUNNING_XLATER {
  command_type t;
  int32_t remoteid;
  int32_t id;
  float rotate;
  int32_t decimation;
};

struct __attribute__ ((__packed__)) SRV_PAYLOAD_HEADER {
  command_type t;
  int32_t id;
  int32_t time;
  int32_t frameno;
  sample_type type;
};

struct __attribute__ ((__packed__)) SRV_INFO {
  command_type t;
  int32_t samplerate;
  int64_t frequency;
  int32_t ppm;
  int32_t fftw;
  int32_t autogain;
  int32_t global_gain;
  int32_t if_gain;
  int32_t bb_gain;
  int32_t packetlen;
  int32_t bufsize;
  int32_t maxtaps;
  sample_type type;
};

