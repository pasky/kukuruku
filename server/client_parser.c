#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <err.h>

#include "client_parser.h"
#include "xlate_worker.h"
#include "util.h"
#include "server.h"

#include "c2s.pb-c.h"

#include "bits.h"

extern pthread_mutex_t datamutex;
extern pthread_mutex_t llmutex;
extern SLIST_HEAD(worker_head_t, worker) worker_head;
extern SLIST_HEAD(tcp_cli_head_t, tcp_cli_t) tcp_cli_head;

extern int32_t samplerate;
extern int64_t frequency;
extern int32_t ppm;
extern int32_t fftw;
extern struct current_gain_t gain;

extern int32_t sdr_cptr;
extern int32_t rec_cptr;
extern int32_t rec_stop;
extern char* recpath;

extern FILE * sdr_cmd;

void msg_running_xlater(tcp_cli_t * me, worker * w) {

  C2s__SRVRUNNINGXLATER s = C2S__SRV__RUNNING__XLATER__INIT;

  s.id = w->wid;
  s.remoteid = w->remoteid;
  s.rotate = w->rotate;
  s.decimation = w->decim;

  // First send the new xlater info with provided ID to the originating client
  size_t len = c2s__srv__running__xlater__get_packed_size(&s);
  void * buf = malloc(len);
  c2s__srv__running__xlater__pack(&s, buf);

  uint32_t size = len + sizeof(int32_t); LE32(&size);
  int32_t mtype = RUNNING_XLATER; LE32(&mtype);

  if(me) {
    writen(me->fd, &size, sizeof(size));
    writen(me->fd, &mtype, sizeof(mtype));
    writen(me->fd, buf, len);
  }

  // then change the ID to -1 and broadcast it to all clients
  s.remoteid = -1;

  len = c2s__srv__running__xlater__get_packed_size(&s);
  buf = realloc(buf, len);
  c2s__srv__running__xlater__pack(&s, buf);

  size = len + sizeof(int32_t); LE32(&size);

  tcp_cli_t * client;
  SLIST_FOREACH(client, &tcp_cli_head, next) {
    if(client != me) {
      writen(client->fd, &size, sizeof(size));
      writen(client->fd, &mtype, sizeof(mtype));
      writen(client->fd, buf, len);
    }
  }

  free(buf);
}

void msg_server_info(tcp_cli_t * me, bool toall) {
  C2s__SRVINFO s = C2S__SRV__INFO__INIT;

  pthread_mutex_lock(&llmutex);

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

  size_t len = c2s__srv__info__get_packed_size(&s);
  void * buf = malloc(len);
  c2s__srv__info__pack(&s, buf);

  uint32_t size = len + sizeof(int32_t); LE32(&size);
  int32_t mtype = INFO; LE32(&mtype);

  if(!toall) {
    writen(me->fd, &size, sizeof(size));
    writen(me->fd, &mtype, sizeof(mtype));
    writen(me->fd, buf, len);
  } else {
    tcp_cli_t * client;
    SLIST_FOREACH(client, &tcp_cli_head, next) {
      writen(client->fd, &size, sizeof(size));
      writen(client->fd, &mtype, sizeof(mtype));
      writen(client->fd, buf, len);
    }
  }

  pthread_mutex_unlock(&llmutex);

  free(buf);
}

void msg_destroyed_xlater(int32_t xid) {
  C2s__SRVDESTROYEDXLATER s = C2S__SRV__DESTROYED__XLATER__INIT;

  pthread_mutex_lock(&llmutex);

  s.id = xid;

  size_t len = c2s__srv__destroyed__xlater__get_packed_size(&s);
  void * buf = malloc(len);
  c2s__srv__destroyed__xlater__pack(&s, buf);

  uint32_t size = len + sizeof(int32_t); LE32(&size);
  int32_t mtype = DESTROYED_XLATER; LE32(&mtype);

  tcp_cli_t * client;
  SLIST_FOREACH(client, &tcp_cli_head, next) {
    writen(client->fd, &size, sizeof(size));
    writen(client->fd, &mtype, sizeof(mtype));
    writen(client->fd, buf, len);
  }

  pthread_mutex_unlock(&llmutex);

  free(buf);
}

int parse_client_req(tcp_cli_t * me, const uint8_t * buf2, int32_t len) {
  int type = ((int*)buf2)[0]; LE32(&type);

  const uint8_t * buf = buf2 + sizeof(int32_t);
  len -= sizeof(int32_t); // strip message type

  if(type == CREATE_XLATER) {
    C2s__CLICREATEXLATER *s;
    s = c2s__cli__create__xlater__unpack(NULL, len, buf);

    size_t tapslen = s->n_taps;
    float * taps = malloc(tapslen * sizeof(float));
    memcpy(taps, s->taps, tapslen * sizeof(float));

    pthread_mutex_lock(&llmutex);

    worker * w = create_xlate_worker(s->rotate, s->decimation, s->startframe, taps, tapslen);
    w->remoteid = s->remoteid;
    msg_running_xlater(me, w);

    pthread_mutex_unlock(&llmutex);

    c2s__cli__create__xlater__free_unpacked(s, NULL);

  } else if(type == ENABLE_XLATER) {
    C2s__CLIENABLEXLATER *s;
    s = c2s__cli__enable__xlater__unpack(NULL, len, buf);

    pthread_mutex_lock(&llmutex);

    req_frames * r = malloc(sizeof(req_frames));
    r->wid = s->id;
    r->sampletype = s->type;
    SLIST_INSERT_HEAD(&(me->req_frames_head), r, next);
    printf("enable %i\n", r->wid);

    pthread_mutex_unlock(&llmutex);

    c2s__cli__enable__xlater__free_unpacked(s, NULL);

  } else if(type == DISABLE_XLATER) {
    C2s__CLIDISABLEXLATER *s;
    s = c2s__cli__disable__xlater__unpack(NULL, len, buf);

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

    c2s__cli__disable__xlater__free_unpacked(s, NULL);

  } else if(type == MODIFY_XLATER) {
    C2s__CLIMODIFYXLATER *s;
    s = c2s__cli__modify__xlater__unpack(NULL, len, buf);

    size_t tapslen = s->n_newtaps;

    pthread_mutex_lock(&llmutex);

    worker * w;
    SLIST_FOREACH(w, &worker_head, next) {
      if(w->wid == s->localid) {
        if(tapslen != 0) {
          float * taps = malloc(tapslen * sizeof(float));
          memcpy(taps, s->newtaps, tapslen * sizeof(float));
          w->newtaps = taps;
          w->newtapslen = tapslen;
        }
        w->rotate = s->rotate;
        break;
      }
    }

    pthread_mutex_unlock(&llmutex);

    if(w) {
      msg_running_xlater(me, w);
    }

    c2s__cli__modify__xlater__free_unpacked(s, NULL);

  } else if(type == LIST_XLATERS) {
    worker * w;

    pthread_mutex_lock(&llmutex);

    SLIST_FOREACH(w, &worker_head, next) {
      msg_running_xlater(me, w);
    }

    pthread_mutex_unlock(&llmutex);

  } else if(type == DESTROY_XLATER) {
    C2s__CLIDESTROYXLATER *s;
    s = c2s__cli__destroy__xlater__unpack(NULL, len, buf);

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

    msg_destroyed_xlater(s->id);

    c2s__cli__destroy__xlater__free_unpacked(s, NULL);

  } else if(type == GET_INFO) {

    msg_server_info(me, false);
    
  } else if(type == RECORD_START) {
    C2s__CLIRECORDSTART *s;
    s = c2s__cli__record__start__unpack(NULL, len, buf);

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
    if(asprintf(&recpath, "rec-%li-%i", time(0), samplerate) == -1) {
      err(1, "asprintf");
    }

    pthread_mutex_unlock(&datamutex);

    c2s__cli__record__start__free_unpacked(s, NULL);

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
    C2s__CLISETGAIN *s;
    s = c2s__cli__set__gain__unpack(NULL, len, buf);

    pthread_mutex_lock(&llmutex);

    char type = SDR_IFACE_GAIN;
    fwrite(&type, sizeof(char), 1, sdr_cmd);
    fwrite(&(s->autogain), sizeof(int32_t), 1, sdr_cmd);
    fwrite(&(s->global_gain), sizeof(int32_t), 1, sdr_cmd);
    fwrite(&(s->if_gain), sizeof(int32_t), 1, sdr_cmd);
    fwrite(&(s->bb_gain), sizeof(int32_t), 1, sdr_cmd);
    fflush(sdr_cmd);

    gain.autogain = s->autogain;
    gain.global_gain = s->global_gain;
    gain.if_gain = s->if_gain;
    gain.bb_gain = s->bb_gain;

    pthread_mutex_unlock(&llmutex);

    msg_server_info(NULL, true);

    c2s__cli__set__gain__free_unpacked(s, NULL);

  } else if(type == RETUNE) {
    C2s__CLIRETUNE *s;
    s = c2s__cli__retune__unpack(NULL, len, buf);

    pthread_mutex_lock(&llmutex);

    char type = SDR_IFACE_TUNE;
    fwrite(&type, sizeof(char), 1, sdr_cmd);
    fwrite(&(s->freq), sizeof(int64_t), 1, sdr_cmd);
    fflush(sdr_cmd);

    frequency = s->freq;

    pthread_mutex_unlock(&llmutex);

    msg_server_info(NULL, true);

    c2s__cli__retune__free_unpacked(s, NULL);

  } else if(type == SET_PPM) {
    C2s__CLISETPPM *s;
    s = c2s__cli__set__ppm__unpack(NULL, len, buf);

    pthread_mutex_lock(&llmutex);

    char type = SDR_IFACE_PPM;
    fwrite(&type, sizeof(char), 1, sdr_cmd);
    fwrite(&(s->ppm), sizeof(int32_t), 1, sdr_cmd);
    fflush(sdr_cmd);

    ppm = s->ppm;

    pthread_mutex_unlock(&llmutex);

    msg_server_info(NULL, true);

    c2s__cli__set__ppm__free_unpacked(s, NULL);

  } else {
    fprintf(stderr, "Unknown type %i\n", type);
  }

  return 0;
}

