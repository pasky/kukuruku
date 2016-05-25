CC = gcc
SWIG = swig3.0

CFLAGS = -Wall -lm -lvolk -std=gnu99 -O3 -g -ggdb3

all: xlater

.PHONY: clean xlater

xlater: v-swig v-wrap v-so

v-swig: 
	$(SWIG) -python xlater.i

v-wrap: v-swig
	$(CC) $(CFLAGS) -c -fpic xlater.c xlater_wrap.c -I/usr/include/python2.7

v-so: v-wrap
	$(CC) $(CFLAGS) -shared xlater.o xlater_wrap.o -o _xlater.so


clean:
	rm later.o _xlater.so xlater_wrap.c xlater_wrap.o

