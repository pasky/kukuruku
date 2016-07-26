#ifndef SOCKET_H
#define SOCKET_H

#include <sys/queue.h>
#include <pthread.h>
#include <stdbool.h>
#include "sample_type.h"

void network_listener(char*, char*);

// One chainlink of a linked list describing subscribed xlaters (tcp_cli_t.req_frames_head)
typedef struct req_frames {
  int wid;
  sample_type sampletype;
  SLIST_ENTRY(req_frames) next;
} req_frames;


// One chainlink of a linked list with info about TCP client.
typedef struct tcp_cli_t {
  int fd;        // socket fd
  pthread_t thr; // client_read_thr
  bool spectrum; // do we send spectrum measurements to this client?
  bool histo;    // do we send histogram measurements to this client?

  SLIST_HEAD(req_frames_head, req_frames) req_frames_head; // linked list of subscribed xlaters

  SLIST_ENTRY(tcp_cli_t) next; // queue(3) next item
} tcp_cli_t;

#endif
