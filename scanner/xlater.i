%include <pybuffer.i>

%pybuffer_mutable_binary(char * _rotpos, size_t rotposlen);
%pybuffer_mutable_binary(char * _firpos, size_t firposlen);

%module xlater
%{
  int xdump(char * buf, size_t buflen, char * carry, size_t carrylen, char * _taps, size_t tapslen, int decim, float rotator, char * _rotpos, size_t rotposlen, char * _firpos, size_t firposlen, int fd);
%}

%include xlater.c
