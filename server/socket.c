#define _GNU_SOURCE
#include <stdio.h>
#include <errno.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <string.h>
#include <pthread.h>
#include <stdbool.h>
#include <err.h>
#include <arpa/inet.h>

#include <sys/queue.h>

#include "socket.h"
#include "util.h"
#include "client_parser.h"
#include "bits.h"

SLIST_HEAD(tcp_cli_head_t, tcp_cli_t) tcp_cli_head = SLIST_HEAD_INITIALIZER(tcp_cli_head);
extern pthread_mutex_t llmutex;

extern char * sdr_cmd_file;
extern FILE * sdr_cmd;

int bind_me(char * port, const char * address, bool wildcard) {

  struct addrinfo hints;
  struct addrinfo *result, *rp;
  int s, sfd;

  memset(&hints, 0, sizeof (struct addrinfo));
  hints.ai_family = AF_UNSPEC;     // Allow IPv4 or IPv6
  hints.ai_socktype = SOCK_STREAM; // TCP
  hints.ai_flags = AI_PASSIVE;     // bind all
  hints.ai_protocol = 0;           // Any protocol
  hints.ai_canonname = NULL;
  hints.ai_addr = NULL;
  hints.ai_next = NULL;

  if(wildcard) {
    s = getaddrinfo(NULL, port, &hints, &result);
  } else {
    s = getaddrinfo(address, port, &hints, &result);
  }

  if (s != 0) {
    err(EXIT_FAILURE, "getaddrinfo: %s\n", gai_strerror(s));
  }

  /*  getaddrinfo() returns a list of address structures.
      Try each address until we successfully bind(2).
      If socket(2) (or bind(2)) fails, we (close the socket
      and) try the next address. */

  for (rp = result; rp != NULL; rp = rp->ai_next) {

    if (rp->ai_family == AF_INET6) {
      char * buf = safe_malloc(INET6_ADDRSTRLEN);
      struct sockaddr_in * saddr = (struct sockaddr_in *)
          rp->ai_addr;
      if (inet_ntop(AF_INET6, &(saddr->sin_addr), buf,
          INET6_ADDRSTRLEN)) {
        printf("Trying (v6) %s\n", buf);
      } else {
        printf("ntop err\n");
      }
      free(buf);
    } else if (rp->ai_family == AF_INET) {
      char * buf = safe_malloc(INET_ADDRSTRLEN);
      struct sockaddr_in * saddr = (struct sockaddr_in *)
          rp->ai_addr;
      if (inet_ntop(AF_INET, & (saddr->sin_addr), buf,
          INET_ADDRSTRLEN)) {
        printf("Trying (v4) %s\n", buf);
      } else {
        printf("ntop err\n");
      }
      free(buf);
    } else if (rp->ai_family == AF_INET) {
      char * buf = safe_malloc(INET_ADDRSTRLEN);
      struct sockaddr_in * saddr = (struct sockaddr_in *)
          rp->ai_addr;
      if (inet_ntop(AF_INET, & (saddr->sin_addr), buf,
          INET_ADDRSTRLEN)) {
        printf("Trying (v4) %s\n", buf);
      } else {
        printf("ntop err\n");
      }
      free(buf);
    }

    // see https://sourceware.org/bugzilla/show_bug.cgi?id=9981
    //if (rp->ai_family == AF_INET) {
      // they don't have the fix in Debian yet
      // just remove it if you expect sane behavior of
      // getaddrinfo
    //  continue;
    //}

    sfd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);

    int enable = 1;
    if (setsockopt(sfd, SOL_SOCKET, SO_REUSEADDR, &enable,
        sizeof (int)) < 0) {
      perror("setsockopt(SO_REUSEADDR) failed");
    }

    if (sfd == -1) {
      continue;
    }

    if (bind(sfd, rp->ai_addr, rp->ai_addrlen) == 0) {
      fprintf(stderr, " ...bound OK fd %i\n", sfd);
      break;
    }

    close(sfd);
  }

  if (rp == NULL) { /* No address succeeded */
    err(EXIT_FAILURE, "Could not bind\n");
  }

  freeaddrinfo(result); /* No longer needed */

  return sfd;

}

void * client_read_thr(void * param) {

  tcp_cli_t * me = (tcp_cli_t*) param;

  SLIST_INIT(&(me->req_frames_head));

  ssize_t ret;

  while(1) {
    int32_t size;
    ret = readn(me->fd, &size, sizeof(int32_t)); LE32(&size);
    if(ret <= 0) {
      break;
    }

    if(size <= 0 || size > 1024*1024) {
      fprintf(stderr, "Read garbage size: %i\n", size);
      break;
    }
    uint8_t * buf = (uint8_t*) safe_malloc(size);
    ret = readn(me->fd, buf, size);
    if(ret < size) {
      free(buf);
      break;
    }
    int res = parse_client_req(me, buf, size);
    free(buf);
    if(res < 0) {
      break;
    }
  }

  pthread_mutex_lock(&llmutex);
  close(me->fd);
  SLIST_REMOVE(&tcp_cli_head, param, tcp_cli_t, next);
  pthread_mutex_unlock(&llmutex);
  free(param);
  return NULL;

}

void network_listener(char * host, char * port) {

  sdr_cmd = fopen(sdr_cmd_file, "w");

  int sockfd = bind_me(port, host, false);
  listen(sockfd, 4);
  int newsockfd;

  SLIST_INIT(&tcp_cli_head);

  while(1) {
    printf("TCP server listening.\n");
    newsockfd = accept(sockfd, NULL, NULL);

    if (newsockfd < 0) {
      perror("ERROR on accept");
      continue;
    }

    pthread_t thread_id;
    tcp_cli_t * cli = safe_malloc(sizeof(tcp_cli_t));
    cli->fd = newsockfd;

    pthread_mutex_lock(&llmutex);
    SLIST_INSERT_HEAD(&tcp_cli_head, cli, next);
    pthread_mutex_unlock(&llmutex);
    cli->thr = thread_id;

    int ret = pthread_create(&thread_id, NULL, &client_read_thr, (void*)cli);
    if(ret < 0) {
      err(EXIT_FAILURE, "Cannot create client thread");
    }
    pthread_setname_np(thread_id, "client_read_t");

    pthread_detach(thread_id);

  }

  close(sockfd);

}
