#pragma once
#ifndef CLIENT_PARSER_H
#define CLIENT_PARSER_H

#include "socket.h"
#include "worker.h"
#include "sample_type.h"

int parse_client_req(tcp_cli_t *, const uint8_t *, int32_t);

enum special_payload_type {
  SPECTRUM = -1, // this payload containt spectrum measurements
  HISTO = -2, // this payload contains histogram
// any nonnegative number -> this payload contains data for that xlater
};

typedef enum command_type {
  RECORD_START = 2,
  RECORD_STOP = 19,
  CREATE_XLATER = 3,
  LIST_XLATERS = 4, // tells the server to send SRV_RUNNING_XLATER for all xlaters
  DESTROY_XLATER = 5,
  ENABLE_XLATER = 6,
  DISABLE_XLATER = 7,
  SET_GAIN = 8,
  RETUNE = 9,
  SET_PPM = 10,
  SET_HISTO_FFT = 11,
  SET_RATE = 12,
  ENABLE_SPECTRUM = 13, // tells the server we want to receive spectrum measurements
  DISABLE_SPECTRUM = 14,
  ENABLE_HISTO = 15,
  DISABLE_HISTO = 16,
  GET_INFO = 17, // request SRV_INFO
  MODIFY_XLATER = 18,

  PAYLOAD = 256,
  DUMPED = 257,
  RUNNING_XLATER = 258,
  INFO = 259,
  DESTROYED_XLATER = 260,
} command_type;

// Now the payload message, the only one that is not protobuf'd (for efficiency reasons)
struct __attribute__ ((__packed__)) SRV_PAYLOAD_HEADER {
  command_type t; // set to PAYLOAD
  int32_t id;     // xlater ID or SPECTRUM or HISTO
  int32_t time;   // timestamp when this has been recorded
  int32_t frameno; // frame number of this frame
  sample_type type; // format of samples
};


/* Now specification of osmosdr control interface (server sends this to the pipe given by -i parameter)
 * 
 * Every time, a header is sent and then specific payload follows
 */
typedef enum sdr_iface {
  SDR_IFACE_TUNE = 1, // int64_t follows
  SDR_IFACE_PPM = 2,  // int32_t follows
  SDR_IFACE_GAIN = 3, // 4 int32_ts follow
} sdr_iface;


#endif
