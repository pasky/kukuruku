#ifndef CONSTANTS_H

#define CONSTANTS_H

#define SDRPACKETSIZE (512*1024)
#define BUFSIZE 64
#define MAXTAPS 4096

#define COMPLEX 2

#define MEGA 1000000
#define GIGA 1000000000

#define WRITE_FRAMES_SYNC 2

#define HISTOGRAM_RES 256

#define MIN(a,b) (((a)<(b))?(a):(b))
#define MAX(a,b) (((a)>(b))?(a):(b))
#define CLAMP(x, lower, upper) (MIN(upper, MAX(x, lower)))

#endif
