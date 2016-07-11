#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <unistd.h>
#include <endian.h>

#include <err.h>

#include <volk/volk.h>

#include <sys/param.h>
#include <pthread.h>
#include <poll.h>
#include <stdbool.h>

#include <getopt.h>

#include "constants.h"
#include "worker.h"
#include "xlate_worker.h"
#include "sdr_packet.h"
#include "socket.h"
#include "util.h"
#include "client_parser.h"
#include "metadata.h"
#include "server.h"
#include "bits.h"

#include <errno.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>

int32_t sdr_cptr = -1;
int32_t send_cptr = -1;
int32_t rec_cptr = INT32_MIN;
int32_t rec_stop = 0;
char * recpath;

sdr_packet sdr_inbuf[BUFSIZE];

pthread_t sdr_thread;
pthread_t socket_thread;

pthread_mutex_t llmutex = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t datamutex = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t datacond = PTHREAD_COND_INITIALIZER;

extern SLIST_HEAD(tcp_cli_head_t, tcp_cli_t) tcp_cli_head;

char * sdr_cmd_file;
FILE * sdr_cmd;
char * sdr_pipe_file;
FILE * sdr_pipe;

int32_t samplerate = -1;
int64_t frequency = 100e6;
int32_t ppm = INT32_MIN;
int32_t fftw = FFTSIZE;
struct current_gain_t gain;

SLIST_HEAD(worker_head_t, worker) worker_head = SLIST_HEAD_INITIALIZER(worker_head);

// Allocate SDR input buffer
void allocate_sdr_buf() {
  size_t align = volk_get_alignment();
  for(int i = 0; i<BUFSIZE; i++) {
    sdr_inbuf[i].data = volk_malloc(COMPLEX * sizeof(float) * SDRPACKETSIZE, align);
    sdr_inbuf[i].histo = malloc(sizeof(uint16_t) * HISTOGRAM_RES);
    if(!sdr_inbuf[i].data) {
      err(1, "Cannot allocate SDR input buffer");
    }
  }
}

void * sdr_read_thr(void * a) {
  // open the pipe we are reading from
  sdr_pipe = fopen(sdr_pipe_file, "r");

  while(1) {

    /* Handle recording.
     * We assume that here might be a bottleneck - the hard drive.
     * Maybe we might memcpy the buffer aside and then do slow writting in a separate
     *  thread or use asyncio, but for now it seems that this approach works reasonably
     *  well unless you are using a Raspberry Pi with a slow SD card, but then you are
     *  screwed anyway... */

    bool locked = true;
    pthread_mutex_lock(&datamutex);
    int32_t _rec_cptr = rec_cptr;
    int32_t _rec_stop = rec_stop;

    if(_rec_cptr != INT32_MIN && _rec_cptr <= _rec_stop) {
      char * cfilepath;
      char * metapath;

      asprintf(&cfilepath, "%s.cfile", recpath);
      asprintf(&metapath, "%s.txt", recpath);

      FILE * cfile = fopen(cfilepath, "ab");
      FILE * metafile = fopen(metapath, "ab");
      // unlock so other threads can work while we wait for the disk
      pthread_mutex_unlock(&datamutex);
      locked = false;
      for(int i = 0; i<WRITE_FRAMES_SYNC; i++) {
        sdr_packet * p = &(sdr_inbuf[(_rec_cptr)%BUFSIZE]);

        fwrite(p->data, SDRPACKETSIZE*COMPLEX * sizeof(float), 1, cfile);

        char * metaline;
        asprintf(&metaline, "block %zu time %i freq %" PRId64 "\n",
          SDRPACKETSIZE*COMPLEX * sizeof(float),
          p->timestamp,
          p->frequency);

        fwrite(metaline, strlen(metaline), 1, metafile);

        free(metaline);

        _rec_cptr++;
        if(_rec_cptr > sdr_cptr) {
          break;
        }
      }
      fclose(cfile);
      fclose(metafile);
      free(cfilepath);
      free(metapath);
    }

    // We wish to write packet sdr_cptr+1.

    if(!locked) {
      pthread_mutex_lock(&datamutex);
    }

    rec_cptr = _rec_cptr;

    int slotsize = SDRPACKETSIZE * COMPLEX * sizeof(float);
    if(sdr_cptr % 10 == 0) {
      printf("SDR buffer: %i/%iM used\n", (slotsize*(sdr_cptr+1-send_cptr))/MEGA, (slotsize*BUFSIZE)/MEGA);
    }

    if(send_cptr < sdr_cptr+1 - BUFSIZE) {
      fprintf(stderr,"SDR data overflow!\n");
      pthread_cond_wait(&datacond, &datamutex);
      pthread_mutex_unlock(&datamutex);
      continue;
    }


    // read packet from sdr
    int base = (sdr_cptr+1)%BUFSIZE;
    pthread_mutex_unlock(&datamutex);

    size_t r = fread(sdr_inbuf[base].data, COMPLEX*sizeof(float), SDRPACKETSIZE, sdr_pipe);
    if(r != SDRPACKETSIZE) {
      err(1, "short read from sdr at frame %i (%zu, %i)\n", sdr_cptr, r, SDRPACKETSIZE);
    }
    sdr_inbuf[base].timestamp = time(0);
    sdr_inbuf[base].frameno = sdr_cptr;
    sdr_inbuf[base].frequency = frequency;
    calc_spectrum(&(sdr_inbuf[base]), 1, 10240);
    calc_histogram(&(sdr_inbuf[base]), 65535);

    // signal that new data are available
    pthread_mutex_lock(&datamutex);
    sdr_cptr++;
    pthread_cond_broadcast(&datacond);
    pthread_mutex_unlock(&datamutex);
  }
}

void * socket_write_thr(void * a) {
  while(1) {
    // We wish to read packet send_cptr+1

    pthread_mutex_lock(&llmutex);

    tcp_cli_t * client;
    bool willwait = true;

    // projdu všechny workery, zapisuju dokud jejich last_written > send_cptr, send_cptr++
    worker * w;
    worker * finished = NULL;
    SLIST_FOREACH(w, &worker_head, next) {
      if(w->enabled) {

        pthread_mutex_lock(&datamutex);
        int _last_written = w->last_written;
        int _send_cptr = w->send_cptr;
        pthread_mutex_unlock(&datamutex);

        while(_last_written > _send_cptr) {
          SLIST_FOREACH(client, &tcp_cli_head, next) {
            req_frames * frm;
            SLIST_FOREACH(frm, &(client->req_frames_head), next) {
              if(frm->wid == w->wid) {

                int bufptr = (_send_cptr+1) % BUFSIZE;

                int plen = w->outbuf[bufptr].len;

                struct SRV_PAYLOAD_HEADER ph;

                ph.t = PAYLOAD;             LE32(&(ph.t));
                ph.id = w->wid;             LE32(&(ph.id));
                ph.type = frm->sampletype;  LE32(&(ph.type));

                if(frm->sampletype == F32) {
                  int32_t size = sizeof(ph) + plen; LE32(&size);
                  writen(client->fd, &size, sizeof(size));
                  writen(client->fd, &ph, sizeof(ph));
#if TARGET_ENDIAN == OUR_ENDIAN
                  writen(client->fd, w->outbuf[bufptr].data, plen);
#else
                  for(int i = 0; i<(plen/sizeof(float)); i++) {
                    float sample = ((float*)(w->outbuf[bufptr].data))[i]; LE32(&sample);
                    writen(client->fd, &sample, sizeof(sample));
                  }
#endif
                } else if(frm->sampletype == I16) {
                  plen /= 2;
                  int32_t size = sizeof(ph) + plen; LE32(&size);
                  writen(client->fd, &size, sizeof(size));
                  writen(client->fd, &ph, sizeof(ph));

                  float scale = ((float)INT16_MAX)/(w->maxval);
                  for(int i = 0; i<(plen*2/sizeof(float)); i++) {
                    int16_t sample = ((float*)(w->outbuf[bufptr].data))[i] * scale;
                    LE16(&sample);
                    writen(client->fd, &sample, sizeof(int16_t));
                  }
                } else if(frm->sampletype == I8) {
                  plen /= 4;
                  int32_t size = sizeof(ph) + plen; LE32(&size);
                  writen(client->fd, &size, sizeof(size));
                  writen(client->fd, &ph, sizeof(ph));

                  float scale = ((float)INT8_MAX)/(w->maxval);
                  for(int i = 0; i<((plen*4)/sizeof(float)); i++) {
                    int8_t sample = ((float*)(w->outbuf[bufptr].data))[i] * scale;
                    writen(client->fd, &sample, sizeof(int8_t));
                  }
                }
                willwait = false;
              }
            }
          }
          _send_cptr++;
        }

        pthread_mutex_lock(&datamutex);
        w->send_cptr = _send_cptr;
        pthread_cond_broadcast(&datacond);
        pthread_mutex_unlock(&datamutex);

      } else { // not enabled, awaiting destruction ... check for thread still alive
        int ret = pthread_kill(w->thr, 0);
        if(ret == ESRCH) { // free
          finished = w;
          SLIST_REMOVE(&worker_head, w, worker, next);
          break;
        }
      }
    }

    if(finished != NULL) {
      free(finished);
      willwait = false;
      pthread_mutex_unlock(&llmutex);
      continue;
    }

    // podívám se na globální send_cptr, zapisuju metadata dokud sdr_cptr > send_cptr, send_cptr++
    pthread_mutex_lock(&datamutex);
    int _sdr_cptr = sdr_cptr;
    int _send_cptr = send_cptr;
    pthread_mutex_unlock(&datamutex);

    while(_sdr_cptr > _send_cptr) {
      SLIST_FOREACH(client, &tcp_cli_head, next) {
        int bufptr = (_send_cptr+1) % BUFSIZE;
        if(client->spectrum) {
          int plen = sdr_inbuf[bufptr].spectrumsize;
          struct SRV_PAYLOAD_HEADER ph;
          int32_t size = sizeof(ph) + plen;       LE32(&size);
          ph.t = PAYLOAD;                         LE32(&(ph.t));
          ph.time = sdr_inbuf[bufptr].timestamp;  LE32(&(ph.time));
          ph.frameno = sdr_inbuf[bufptr].frameno; LE32(&(ph.frameno));
          ph.id = SPECTRUM;                       LE32(&(ph.id));
          writen(client->fd, &size, sizeof(size));
          writen(client->fd, &ph, sizeof(ph));
#if TARGET_ENDIAN == OUR_ENDIAN
          writen(client->fd, sdr_inbuf[bufptr].spectrum, plen);
#else
          for(int i = 0; i<plen/sizeof(float); i++) {
            float sample = ((float*)(sdr_inbuf[bufptr].spectrum))[i];
            LE32(&sample);
            writen(client->fd, &sample, sizeof(sample));
          }
#endif
          willwait = false;
        }
        if(client->histo) {
          int plen = HISTOGRAM_RES * sizeof(uint16_t);
          struct SRV_PAYLOAD_HEADER ph;
          int32_t size = sizeof(ph) + plen;         LE32(&size);
          ph.t = PAYLOAD;                           LE32(&(ph.t));
          ph.time = sdr_inbuf[bufptr].timestamp;    LE32(&(ph.time));
          ph.id = HISTO;                            LE32(&(ph.id));
          writen(client->fd, &size, sizeof(size));
          writen(client->fd, &ph, sizeof(ph));
#if TARGET_ENDIAN == OUR_ENDIAN
          writen(client->fd, sdr_inbuf[bufptr].histo, plen);
#else
          for(int i = 0; i<plen/sizeof(uint16_t); i++) {
            uint16_t sample = ((uint16_t*)(sdr_inbuf[bufptr].histo))[i];
            LE16(&sample);
            writen(client->fd, &sample, sizeof(sample));
          }
#endif
          willwait = false;
        }
      }

      _send_cptr++;
    }

    pthread_mutex_lock(&datamutex);
    send_cptr = _send_cptr;
    pthread_cond_broadcast(&datacond);
    pthread_mutex_unlock(&datamutex);

    pthread_mutex_unlock(&llmutex);

    // pokud jsem nic nezapsal, čekám na cond
    if(willwait) {
      poll(NULL, 0, 10);
    }

  }
}

void create_read_write_threads() {

  int ret = pthread_create(&sdr_thread, NULL, &sdr_read_thr, NULL);
  if(ret != 0) {
    err(1, "Cannot create SDR thread!\n");
  }
  pthread_setname_np(sdr_thread, "sdr_read_thr");

  ret = pthread_create(&socket_thread, NULL, &socket_write_thr, NULL);
  if(ret != 0) {
    err(1, "Cannot create socket thread!\n");
  }
  pthread_setname_np(socket_thread, "socket_write_t");

}

void usage(char * me) {
  printf("usage: %s -s rate -p ppm -f frequency -i cmdpipe -o sdrpipe\n", me);
  printf("\n");
  exit(1);
}

int main(int argc, char **argv) {

  char * host = "localhost";
  char * port = "4444";

  /* Command line opts */
  int opt;
  while ((opt = getopt(argc, argv, "s:f:p:g:i:o:r:h:t:w:")) != -1) {
    switch (opt) {
      case 's':
        samplerate = atoi(optarg);
        break;
      case 'f':
        frequency = atoi(optarg);
        break;
      case 'p':
        ppm = atoi(optarg);
        break;
      case 'r':
        samplerate = atoi(optarg);
        break;
      case 'g':
        gain.autogain = 1;
        gain.global_gain = atoi(optarg);
        gain.if_gain = atoi(optarg);
        gain.bb_gain = atoi(optarg);
        break;
      case 'i':
        sdr_cmd_file = optarg;
        break;
      case 'o':
        sdr_pipe_file = optarg;
        break;
      case 't':
        port = optarg;
        break;
      case 'w':
        fftw = atoi(optarg);
        break;
      case 'h':
        host = optarg;
        break;
      default:
        usage(argv[0]);
    }
  }

  if(frequency < 0 || samplerate < 0 || ppm == INT32_MIN ||
   sdr_pipe_file == NULL || sdr_cmd_file == NULL) {
    usage(argv[0]);
  }

  sigset_t set;
  sigemptyset(&set);
  sigaddset(&set, SIGPIPE);
  int s = pthread_sigmask(SIG_BLOCK, &set, NULL);
  if (s != 0)
    err(1, "pthread_sigmask");

  fftw_init(fftw);

  allocate_sdr_buf();

  create_read_write_threads();

  // run network listener in the main thread
  network_listener(host, port);

  // this should never happen
  return EXIT_FAILURE;

}
