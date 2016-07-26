#pragma once
#ifndef CONSTANTS_H
#define CONSTANTS_H

/* Number of samples to read each time we read from SDR
 *  (so it is this*sizeof(complex64) bytes)
 * You want to set this to something between 128 and 1024 Ki.
 */
#define SDRPACKETSIZE (512*1024)

/* Number of packets to keep.
 * So we will allocate SDRPACKETSIZE*8*BUFSIZE bytes of memory. */
#define BUFSIZE 128

/* The longest allowed filter */
#define MAXTAPS 4096

/* Size of spectrum transform. Increase this for better resolution on wideband SDRs. */
#define FFTSIZE 1024

#define WRITE_FRAMES_SYNC 2

#define HISTOGRAM_RES 256




#define COMPLEX 2

#define MEGA 1000000
#define GIGA 1000000000

#define MIN(a,b) (((a)<(b))?(a):(b))
#define MAX(a,b) (((a)>(b))?(a):(b))
#define CLAMP(x, lower, upper) (MIN(upper, MAX(x, lower)))

#endif
