CPP = gcc
CFLAGS = -pedantic -pthread -std=gnu99 -Wall -lprotobuf-c -lm -lvolk -lfftw3f -O3 -g -ggdb3

.PHONY: clean

all: server

OTHINGS = xlate_worker.o server.o socket.o util.o client_parser.o metadata.o c2s.pb-c.o bits.o

c2s.pb-c.c:
	protoc-c --c_out=. c2s.proto

%.o: %.c
	$(CPP) -c $< -o $@ $(INC) $(CFLAGS)

server: c2s.pb-c.c $(OTHINGS)
	$(CPP) $(OTHINGS) -o server $(CFLAGS)

clean:
	rm -fr *.o server c2s.pb-c.h c2s.pb-c.c

