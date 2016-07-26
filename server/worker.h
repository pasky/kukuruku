#ifndef WORKER_H
#define WORKER_H

#include <stdbool.h>
#include "constants.h"
#include <sys/queue.h>

typedef struct worker_packet {
  int len;
  char * data;
} worker_packet;

/* One chainlink of a linked list with all workers we have spawned.
 * Currently we have only xlater_worker, but the goal was to have workers
 *  doing other things (okay, maybe a special worker that uses FFT overlap-add
 *  to accelerate convolution).
 */
typedef struct worker {
  int wid; // worker id
  bool enabled; // set to false to make the worker gracefully exit
  pthread_t thr; // (xlate_)worker_thr
  float rotate;
  int decim;

  /* The worker reads SDR packets from sdr_inbuf and writes them to outbuf.
   * Both are ring-buffers accessed % BUFSIZE
   * send_cptr and last_written are used to show where in the stream we are.
   * send_cptr - ID of the last frame which has been sent to all clients.
   *  so all frames with lower ID are free
   * last_written - ID of the last frame the worker has processed. So all frames
   *  between send_cptr+1 and last_written are ready to be sent to TCP clients.

    -+------+------+------+------+------+------+------+------+-
  ...|      |      |      |      |      |      |      |      |...    %BUFSIZE
    -+------+------+------+------+------+------+------+------+-
   free frames     ^       ready frames        ^       future frames
                send_cptr                last_written

   */
  int32_t last_written;
  int32_t send_cptr;

  /* Changing taps at runtime: 
     - lock datamutex
     - malloc newtaps, memcpy
     - set newtapslen
     - unlock datamutex
     - both old taps and newtaps will be freed by the worker
  */
  float * taps;
  float * newtaps;

  float maxval; // maximum value of a sample the worker can produce given it is fed with samples
                //  from range [-1, 1]. Usually about 1.5. Used when scaling samples to integer types.
                // The value is set by calc_max_amplitude by create_xlate_worker or by the xlater itself
                //  when taps are changed.
  int tapslen;  // Ntaps (i.e. bytes/sizeof(float32))
  int newtapslen;

  // Maximum size of one filtered and decimated frame.
  // It can actually be one sample shorter if SDRPACKETSIZE is not divisible by decimation.
  size_t maxoutsize;

  int32_t remoteid; // client-set ID (probably not needed here)

  worker_packet outbuf[BUFSIZE];
  SLIST_ENTRY(worker) next;
} worker;

#endif
