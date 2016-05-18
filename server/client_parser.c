#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <string.h>

#include "client_parser.h"
#include "xlate_worker.h"
#include "util.h"

extern pthread_mutex_t datamutex;
extern pthread_mutex_t llmutex;
extern SLIST_HEAD(worker_head_t, worker) worker_head;
extern SLIST_HEAD(tcp_cli_head_t, tcp_cli_t) tcp_cli_head;

extern int32_t samplerate;
extern int64_t frequency;
extern int32_t ppm;
extern int32_t fftw;
extern struct CLI_SET_GAIN gain;

extern int32_t sdr_cptr;
extern int32_t rec_cptr;
extern int32_t rec_stop;
extern char* recpath;

extern FILE * sdr_cmd;

#define HEADER_LEN sizeof(int)
#define S_ASSERT(s) if(len - HEADER_LEN < s) {\
                      fprintf(stderr, "Received packet too short\n"); \
                      return -1; \
                    }

void msg_running_xlater(tcp_cli_t * me, worker * w) {
  struct SRV_RUNNING_XLATER s;

  int32_t size = sizeof(s);
  writen(me->fd, &size, sizeof(size));

  s.t = RUNNING_XLATER;
  s.id = w->wid;
  s.remoteid = w->remoteid;
  s.rotate = w->rotate;
  s.decimation = w->decim;
  writen(me->fd, &s, size);
}

void msg_server_info(tcp_cli_t * me) {
  struct SRV_INFO s;

  int32_t size = sizeof(s);
  writen(me->fd, &size, sizeof(size));

  s.t = INFO;
  s.samplerate = samplerate;
  s.frequency = frequency;
  s.ppm = ppm;
  s.fftw = fftw;

  s.autogain = gain.autogain;
  s.global_gain = gain.global_gain;
  s.if_gain = gain.if_gain;
  s.bb_gain = gain.bb_gain;

  s.packetlen = SDRPACKETSIZE;
  s.bufsize = BUFSIZE;
  s.maxtaps = MAXTAPS;

  writen(me->fd, &s, size);
}

int parse_client_req(tcp_cli_t * me, char * buf, int32_t len) {
  int type = ((int*)buf)[0];
  buf += 4;

  if(type == CREATE_XLATER) {
    S_ASSERT(sizeof(struct CLI_CREATE_XLATER));

    struct CLI_CREATE_XLATER * s = (struct CLI_CREATE_XLATER *)buf;

    int tapslen = len - HEADER_LEN - sizeof(struct CLI_CREATE_XLATER);
    float * taps = malloc(tapslen);
    memcpy(taps, buf + HEADER_LEN + sizeof(struct CLI_CREATE_XLATER), tapslen);

    pthread_mutex_lock(&llmutex);

    worker * w = create_xlate_worker(s->rotate, s->decimation, s->startframe, taps, tapslen/sizeof(float));
    w->remoteid = s->remoteid;
    msg_running_xlater(me, w);

    pthread_mutex_unlock(&llmutex);

  } else if(type == ENABLE_XLATER) {
    S_ASSERT(sizeof(struct CLI_ENABLE_XLATER));

    struct CLI_ENABLE_XLATER * s = (struct CLI_ENABLE_XLATER *)buf;

    pthread_mutex_lock(&llmutex);

    req_frames * r = malloc(sizeof(req_frames));
    r->wid = s->id;
    SLIST_INSERT_HEAD(&(me->req_frames_head), r, next);
    printf("enable %i\n", r->wid);

    pthread_mutex_unlock(&llmutex);

  } else if(type == DISABLE_XLATER) {
    S_ASSERT(sizeof(struct CLI_DISABLE_XLATER));

    struct CLI_DISABLE_XLATER * s = (struct CLI_DISABLE_XLATER *)buf;

    pthread_mutex_lock(&llmutex);

    worker * w;
    tcp_cli_t * client;
    SLIST_FOREACH(w, &worker_head, next) {
      if(w->wid == s->id) {
        SLIST_FOREACH(client, &tcp_cli_head, next) {
          req_frames * frm;
          SLIST_FOREACH(frm, &(client->req_frames_head), next) {
            if(frm->wid == w->wid) {
              SLIST_REMOVE(&(client->req_frames_head), frm, req_frames, next);
              free(frm);
            }
          }
        }
      }
    }

    pthread_mutex_unlock(&llmutex);

  } else if(type == MODIFY_XLATER) {
    S_ASSERT(sizeof(struct CLI_MODIFY_XLATER));

    struct CLI_MODIFY_XLATER * s = (struct CLI_MODIFY_XLATER *)buf;

    int tapslen = len - HEADER_LEN - sizeof(struct CLI_MODIFY_XLATER);
    float * taps = malloc(tapslen);
    memcpy(taps, buf + HEADER_LEN + sizeof(struct CLI_MODIFY_XLATER), tapslen);

    pthread_mutex_lock(&llmutex);

    worker * w;
    SLIST_FOREACH(w, &worker_head, next) {
      if(w->wid == s->localid) {
        if(s->newtaps != 0) {
          w->newtaps = taps;
          w->newtapslen = tapslen/sizeof(float);
        }
        w->rotate = s->rotate;
      }
    }

    pthread_mutex_unlock(&llmutex);

  } else if(type == LIST_XLATERS) {
    worker * w;

    pthread_mutex_lock(&llmutex);

    SLIST_FOREACH(w, &worker_head, next) {
      msg_running_xlater(me, w);
    }

    pthread_mutex_unlock(&llmutex);

  } else if(type == DESTROY_XLATER) {
    S_ASSERT(sizeof(struct CLI_DESTROY_XLATER));

    struct CLI_DESTROY_XLATER * s = (struct CLI_DESTROY_XLATER *)buf;

    pthread_mutex_lock(&llmutex);

    worker * w;
    tcp_cli_t * client;

    SLIST_FOREACH(w, &worker_head, next) {
      if(w->wid == s->id) {
        SLIST_FOREACH(client, &tcp_cli_head, next) {
          req_frames * frm;
          SLIST_FOREACH(frm, &(client->req_frames_head), next) {
            if(frm->wid == w->wid) {
              SLIST_REMOVE(&(client->req_frames_head), frm, req_frames, next);
              free(frm);
            }
          }
        }
        w->enabled = false;
      }
    }

    pthread_mutex_unlock(&llmutex);

  } else if(type == GET_INFO) {

    pthread_mutex_lock(&llmutex);
    msg_server_info(me);
    pthread_mutex_unlock(&llmutex);
    
  } else if(type == RECORD_START) {
    S_ASSERT(sizeof(struct CLI_RECORD_START));

    struct CLI_RECORD_START * s = (struct CLI_RECORD_START *)buf;

    pthread_mutex_lock(&datamutex);

    if(recpath != NULL) {
      free(recpath);
    }

    if(s->startframe == -1) {
      rec_cptr = sdr_cptr;
    } else {
      rec_cptr = s->startframe;
    }

    if(rec_cptr < sdr_cptr - BUFSIZE) {
      fprintf(stderr, "Cannot record that much in history\n");
      rec_cptr = sdr_cptr - BUFSIZE;
    }

    if(rec_cptr < 0) {
      rec_cptr = 0;
    }

    rec_stop = s->stopframe;
    asprintf(&recpath, "rec-%li-%i", time(0), samplerate);

    pthread_mutex_unlock(&datamutex);

  } else if(type == RECORD_STOP) {
    pthread_mutex_lock(&datamutex);
    rec_cptr = INT32_MIN;
    pthread_mutex_unlock(&datamutex);

  } else if(type == ENABLE_SPECTRUM) {
    printf("enabled spectrum\n");
    me->spectrum = true;

  } else if(type == ENABLE_HISTO) {
    me->histo = true;

  } else if(type == SET_GAIN) {
    S_ASSERT(sizeof(struct CLI_SET_GAIN));

    pthread_mutex_lock(&llmutex);

    char type = SDR_IFACE_GAIN;
    fwrite(&type, sizeof(char), 1, sdr_cmd);
    fwrite(buf, sizeof(struct CLI_SET_GAIN), 1, sdr_cmd);
    fflush(sdr_cmd);

    memcpy(&gain, buf, sizeof(struct CLI_SET_GAIN));

    pthread_mutex_unlock(&llmutex);

  } else if(type == RETUNE) {
    S_ASSERT(sizeof(struct CLI_RETUNE));

    pthread_mutex_lock(&llmutex);

    char type = SDR_IFACE_TUNE;
    fwrite(&type, sizeof(char), 1, sdr_cmd);
    fwrite(buf, sizeof(struct CLI_RETUNE), 1, sdr_cmd);
    fflush(sdr_cmd);

    frequency = ((struct CLI_RETUNE *)buf)->freq;

    pthread_mutex_unlock(&llmutex);

  } else if(type == SET_PPM) {
    S_ASSERT(sizeof(struct CLI_SET_PPM));

    pthread_mutex_lock(&llmutex);

    char type = SDR_IFACE_PPM;
    fwrite(&type, sizeof(char), 1, sdr_cmd);
    fwrite(buf, sizeof(struct CLI_SET_PPM), 1, sdr_cmd);
    fflush(sdr_cmd);

    ppm = ((struct CLI_SET_PPM *)buf)->ppm;

    pthread_mutex_unlock(&llmutex);

  } else {
    fprintf(stderr, "Unknown type %i\n", type);
  }

  return 0;
}

