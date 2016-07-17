CC = gcc
SWIG = swig3.0

CFLAGS = -Wall -lm -lvolk -std=gnu99 -O3 -g -ggdb3

all: xlater.py

.PHONY: clean

xlater_wrap.c: xlater.c
	$(SWIG) -python xlater.i

xlater.o: xlater_wrap.c
	$(CC) $(CFLAGS) -c -fpic xlater.c xlater_wrap.c -I/usr/include/python2.7

xlater.py: xlater.o
	$(CC) $(CFLAGS) -shared xlater.o xlater_wrap.o -o _xlater.so


clean:
	rm -f xlater.o _xlater.so xlater_wrap.c xlater_wrap.o xlater.py xlater.pyc

