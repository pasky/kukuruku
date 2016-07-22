#include "util.h"
#include <stddef.h>
#include <unistd.h>
#include <fftw3.h>

ssize_t readn(int fd, void * buf2, int n) {
  char * buf = (char*)buf2;
  int pos = 0;
  while(pos<n) {
    ssize_t j = read(fd, buf+pos, n-pos);
    if(j <= 0) {
      return j;
    }
    pos += j;
  }
  return pos;
}

ssize_t writen(int fd, void * buf2, int n) {
  char * buf = (char*)buf2;
  int pos = 0;
  while(pos<n) {
    ssize_t j = write(fd, buf+pos, n-pos);
    if(j <= 0) {
      return j;
    }
    pos += j;
  }
  return pos;
}

void* safe_malloc(size_t size) {
  void* p = malloc(size);
  if (!p) {
    err(EXIT_FAILURE, "malloc");
  }
  return p;
}

void* volk_safe_malloc(size_t size, size_t align) {
  void* p = volk_malloc(size, align);
  if (!p) {
    err(EXIT_FAILURE, "volk_malloc");
  }
  return p;
}

void* fftwf_safe_malloc(size_t size) {
  void* p = fftwf_malloc(size);
  if (!p) {
    err(EXIT_FAILURE, "volk_malloc");
  }
  return p;
}

