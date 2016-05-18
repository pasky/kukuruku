CPP = gcc
CFLAGS = -pedantic -pthread -std=gnu99 -Wall -lm -lvolk -lfftw3f -O3 -g -ggdb3

all: server

OTHINGS = xlate_worker.o server.o socket.o util.o client_parser.o metadata.o

%.o: %.c
	$(CPP) $(CFLAGS) -c $< -o $@ $(INC)

server: $(OTHINGS)
	$(CPP) $(CFLAGS) $(OTHINGS) -o server

clean:
	rm -fr *.o server

