#ifndef SOCKET_H
#define SOCKET_H

#include <sys/queue.h>
#include <pthread.h>
#include <stdbool.h>
#include "sample_type.h"

void network_listener(char*, char*);

typedef struct req_frames {
  int wid;
  sample_type sampletype;
  SLIST_ENTRY(req_frames) next;
} req_frames;

typedef struct tcp_cli_t {
  int fd;
  pthread_t thr;
  bool spectrum;
  bool histo;

  SLIST_HEAD(req_frames_head, req_frames) req_frames_head;

  SLIST_ENTRY(tcp_cli_t) next;
} tcp_cli_t;

#endif
