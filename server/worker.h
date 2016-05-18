#ifndef WORKER_H
#define WORKER_H

#include <stdbool.h>
#include "constants.h"
#include <sys/queue.h>

typedef struct worker_packet {
  int len;
  char * data;
} worker_packet;

typedef struct worker {
  int wid;
  bool enabled;
  pthread_t thr;
  float rotate;
  int decim;
  int32_t last_written;
  int32_t send_cptr;
  float * taps;
  float * newtaps;
  int tapslen;
  int newtapslen;
  int32_t remoteid;
  worker_packet outbuf[BUFSIZE];
  SLIST_ENTRY(worker) next;
} worker;

#endif
