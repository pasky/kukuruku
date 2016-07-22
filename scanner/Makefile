CC = gcc
SWIG = swig3.0

CFLAGS = -Wall -lm -lvolk -std=gnu99 -O3 -g -ggdb3

all: _xlater.so

.PHONY: clean

xlater_wrap.c: xlater.c
	$(SWIG) -python xlater.i

xlater.o: xlater_wrap.c
	$(CC) -c -fpic xlater.c xlater_wrap.c -I/usr/include/python2.7 $(CFLAGS)

_xlater.so: xlater.o
	$(CC) -shared xlater.o xlater_wrap.o -o _xlater.so $(CFLAGS)


clean:
	rm -f xlater.o _xlater.so xlater_wrap.c xlater_wrap.o xlater.py xlater.pyc

