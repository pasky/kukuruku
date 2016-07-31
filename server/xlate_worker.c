#define _GNU_SOURCE
#include <volk/volk.h>
#include <math.h>

#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <unistd.h>

#include <sys/param.h>
#include <pthread.h>
#include <poll.h>
#include <stdbool.h>
#include <err.h>

#include "constants.h"
#include "worker.h"
#include "xlate_worker.h"
#include "sdr_packet.h"
#include "util.h"

extern int32_t sdr_cptr;
extern int32_t send_cptr;
extern sdr_packet sdr_inbuf[BUFSIZE]; 

extern pthread_mutex_t datamutex;
extern pthread_cond_t datacond;

extern SLIST_HEAD(worker_head_t, worker) worker_head;

int widx;

/* Calculate the maximum amplitude a filter can produce. */
float calc_max_amplitude(float * taps, int tapslen) {

  float acc = 0;
  for(int i = 0; i<tapslen; i++) {
    acc += fabs(taps[i]);
  }

  return acc;

}

/* Rotate the low-pass filter, so it becomes band-pass. */
float * get_complex_taps(float * taps, int tapslen, float rotate) {
  size_t align = volk_get_alignment();
  float * ctaps = volk_safe_malloc(tapslen * COMPLEX * sizeof(float), align);

  for(int i = 0; i<tapslen; i++) {
    ctaps[COMPLEX*i]     = taps[i] * cos(rotate*i);
    ctaps[COMPLEX*i + 1] = taps[i] * sin(rotate*i);
  }
  return ctaps;
}

/* history .. the frame it should start with (or -1 for current frame) */
worker * create_xlate_worker(float rotate, int decim, int history, float * taps, int tapslen) {

  worker * w = calloc(1, sizeof(worker));

  w->rotate = rotate;
  w->decim = decim;
  w->wid = widx;
  w->taps = get_complex_taps(taps, tapslen, rotate);
  w->tapslen = tapslen;

  w->maxval = calc_max_amplitude(taps, tapslen);

  free(taps);

  if(history == -1) {
    w->last_written = sdr_cptr;
  } else {
    w->last_written = history;
    if(w->last_written < sdr_cptr - BUFSIZE) {
      fprintf(stderr, "Cannot play that much in history\n");
      w->last_written = sdr_cptr - BUFSIZE;
    }
  }
  w->send_cptr = w->last_written;

  // allocate space for one more sample, because there might be a fir offset that will make us produce more tham SDRPACKETSIZE/decim
  w->maxoutsize = COMPLEX * sizeof(float) * (SDRPACKETSIZE/decim+1);
  size_t align = volk_get_alignment();

  //workers[wid].outbuf = safe_malloc(sizeof(char*) * BUFSIZE);
  for(int i = 0; i<BUFSIZE; i++) {
    w->outbuf[i].data = volk_safe_malloc(w->maxoutsize, align);
  }

  int ret = pthread_create(&w->thr, NULL, &xlate_worker_thr, (void*) w);
  if(ret < 0) {
    err(EXIT_FAILURE, "cannot create xlater worker thread");
  }
  pthread_setname_np(w->thr, "worker");

  w->enabled = true;

  SLIST_INSERT_HEAD(&worker_head, w, next);

  widx++;

  return w;

}

void * xlate_worker_thr(void *ptr) {
  worker * ctx = (worker*)ptr;

  int32_t mypos = ctx->last_written + 1;

  int fir_offset = 0;

  /* To avoid hassle with complicated FIR evaluation, we allocate *alldata bigger
   *  and copy the end of previous frame to the beginning of it, so we can compute
   *  the filter simply as sum(x_{n-j}*h_{j}) and don't care about overflows.
   * 
   * The interesting fact is that if SDRPACKETSIZE is not divisible by decimation,
   *  the filtered frames will have different lengths.
   */
  float * alldata = calloc(sizeof(float), (SDRPACKETSIZE + MAXTAPS) * COMPLEX);
  float * firout = calloc(1, ctx->maxoutsize);
  lv_32fc_t phase_inc, phase;

  phase = lv_cmake(1.0, 0.0);

  while(1) {
    pthread_mutex_lock(&datamutex);
    if(sdr_cptr <= mypos || ctx->send_cptr <= mypos - BUFSIZE) { // there are no data to process or no free space
      pthread_cond_wait(&datacond, &datamutex);
      pthread_mutex_unlock(&datamutex);
      continue;
    }
    pthread_mutex_unlock(&datamutex);

    phase_inc = lv_cmake(cos(ctx->rotate * ctx->decim), sin(ctx->rotate * ctx->decim));

    memcpy(alldata, alldata+SDRPACKETSIZE*COMPLEX, MAXTAPS * COMPLEX * sizeof(float));
    memcpy(alldata + MAXTAPS, sdr_inbuf[mypos % BUFSIZE].data, SDRPACKETSIZE * COMPLEX * sizeof(float));

    int outsample = 0;
    int i;

    // evaluate the filter
    for(i = fir_offset; i<SDRPACKETSIZE; i+=ctx->decim) {
      lv_32fc_t* dst = (lv_32fc_t*) (firout + outsample*COMPLEX);
      volk_32fc_x2_dot_prod_32fc(dst,
          (lv_32fc_t*) (alldata+(i)*COMPLEX), // src
          (lv_32fc_t*)(ctx->taps), ctx->tapslen); // filter
      outsample++;
    }

    // rotator
    volk_32fc_s32fc_x2_rotator_32fc( (lv_32fc_t*) ctx->outbuf[mypos % BUFSIZE].data, // dst
        (lv_32fc_t*) firout, phase_inc, &phase, outsample);

    // save position so we know where to start evaluation the next frame
    fir_offset = i - SDRPACKETSIZE;

    ctx->outbuf[mypos % BUFSIZE].len = outsample * COMPLEX * sizeof(float);

    pthread_mutex_lock(&datamutex);
    if(ctx->newtaps != NULL) {
      free(ctx->taps);
      ctx->taps = get_complex_taps(ctx->newtaps, ctx->newtapslen, ctx->rotate);
      ctx->tapslen = ctx->newtapslen;
      ctx->maxval = calc_max_amplitude(ctx->newtaps, ctx->newtapslen);
      free(ctx->newtaps);
      ctx->newtaps = NULL;
    }
    if(!ctx->enabled) {
      pthread_mutex_unlock(&datamutex);
      break;
    }
    ctx->last_written = mypos;
    pthread_cond_broadcast(&datacond);
    pthread_mutex_unlock(&datamutex);

    mypos++;

  }

  // gracefully exit -- free and unlock everything...
  for(int i = 0; i<BUFSIZE; i++) {
    volk_free(ctx->outbuf[i].data);
  }
  free(ctx->taps);
  if(ctx->newtaps != NULL) {
    free(ctx->newtaps);
  }
  free(alldata);
  free(firout);

  return NULL;
}
