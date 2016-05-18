#include <stddef.h>
#include <unistd.h> 

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
