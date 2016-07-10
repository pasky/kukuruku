CPP = gcc
CFLAGS = -pedantic -pthread -std=gnu99 -Wall -lprotobuf-c -lm -lvolk -lfftw3f -O3 -g -ggdb3

.PHONY: clean

all: c2s.pb-c.h server

OTHINGS = xlate_worker.o server.o socket.o util.o client_parser.o metadata.o c2s.pb-c.o bits.o

c2s.pb-c.h:
	protoc-c --c_out=. c2s.proto

%.o: %.c
	$(CPP) $(CFLAGS) -c $< -o $@ $(INC)

server: $(OTHINGS)
	$(CPP) $(CFLAGS) $(OTHINGS) -o server

clean:
	rm -fr *.o server c2s.pb-c.h c2s.pb-c.c

