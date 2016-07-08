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

extern int32_t sdr_cptr;
extern int32_t send_cptr;
extern sdr_packet sdr_inbuf[BUFSIZE]; 

extern pthread_mutex_t datamutex;
extern pthread_cond_t datacond;

extern SLIST_HEAD(worker_head_t, worker) worker_head;

int widx;

float calc_max_amplitude(float * taps, int tapslen) {

  float acc = 0;
  for(int i = 0; i<tapslen; i++) {
    acc += fabs(taps[i]);
  }

  return acc;

}

worker * create_xlate_worker(float rotate, int decim, int history, float * taps, int tapslen) {

  worker * w = calloc(1, sizeof(worker));

  w->rotate = rotate;
  w->decim = decim;
  w->wid = widx;
  w->taps = taps;
  w->tapslen = tapslen;

  w->maxval = calc_max_amplitude(taps, tapslen);

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

  int outsize = COMPLEX * sizeof(float) * SDRPACKETSIZE/decim;
  size_t align = volk_get_alignment();

  //workers[wid].outbuf = malloc(sizeof(char*) * BUFSIZE);
  for(int i = 0; i<BUFSIZE; i++) {
    w->outbuf[i].data = volk_malloc(outsize, align);
  }

  int ret = pthread_create(&w->thr, NULL, &xlate_worker_thr, (void*) w);
  if(ret < 0) {
    err(1, "cannot create xlater worker thread");
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
  float * alldata = calloc(sizeof(float), (SDRPACKETSIZE + MAXTAPS) * COMPLEX);
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

    phase_inc = lv_cmake(cos(ctx->rotate), sin(ctx->rotate));

    memcpy(alldata, alldata+SDRPACKETSIZE*COMPLEX, MAXTAPS * COMPLEX * sizeof(float));

    volk_32fc_s32fc_x2_rotator_32fc( (lv_32fc_t*)(alldata + MAXTAPS), // dst
                                     (lv_32fc_t*)(sdr_inbuf[mypos % BUFSIZE].data), // src
                                     phase_inc, &phase, SDRPACKETSIZE); // params

    int outsample = 0;
    int i;

    for(i = fir_offset; i<SDRPACKETSIZE; i+=ctx->decim) {
      volk_32fc_32f_dot_prod_32fc(
          (lv_32fc_t*) (ctx->outbuf[mypos % BUFSIZE].data + outsample*COMPLEX*sizeof(float)), // dst
          (lv_32fc_t*) (alldata+(i)*COMPLEX), // src
          ctx->taps, ctx->tapslen); // filter
      outsample++;
    }
    fir_offset = i - SDRPACKETSIZE;
    ctx->outbuf[mypos % BUFSIZE].len = outsample * COMPLEX * sizeof(float);

    pthread_mutex_lock(&datamutex);
    if(ctx->newtaps != NULL) {
      free(ctx->taps);
      ctx->taps = ctx->newtaps;
      ctx->tapslen = ctx->newtapslen;
      ctx->newtaps = NULL;
      ctx->maxval = calc_max_amplitude(ctx->taps, ctx->tapslen);
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

  for(int i = 0; i<BUFSIZE; i++) {
    volk_free(ctx->outbuf[i].data);
  }
  free(ctx->taps);
  if(ctx->newtaps != NULL) {
    free(ctx->newtaps);
  }
  free(alldata);

  return NULL;
}
