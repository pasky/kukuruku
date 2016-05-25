#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <volk/volk.h>
#include <math.h>
#include <assert.h>

#include <unistd.h>

#define COMPLEX 2

int xdump(char * _buf, size_t buflen, char * _carry, size_t carrylen, char * _taps, size_t tapslen, int decim, float rotator, char * _rotpos, size_t rotposlen, char * _firpos, size_t firposlen, char * outfile) {

  assert(rotposlen == sizeof(lv_32fc_t));
  assert(firposlen == sizeof(int32_t));

  int * firpos = (int*) _firpos;
  float * rotpos = (float*) _rotpos;

  float * taps = (float*) _taps;
  int nsamples = buflen / (sizeof(float)*COMPLEX);

  float * alldata = malloc(sizeof(float) * COMPLEX * (buflen + carrylen));
  lv_32fc_t phase_inc = lv_cmake(cos(rotator), sin(rotator));
  lv_32fc_t* phase = (lv_32fc_t*) _rotpos;

  volk_32fc_s32fc_x2_rotator_32fc((lv_32fc_t*)alldata, // dst
                                  (lv_32fc_t*)_carry, // src
                                   phase_inc, phase, carrylen / (sizeof(float)*COMPLEX)); // params

  volk_32fc_s32fc_x2_rotator_32fc((lv_32fc_t*)(alldata + carrylen / sizeof(float)), // dst
                                  (lv_32fc_t*)_buf, // src
                                   phase_inc, phase, nsamples); // params

  int32_t i;
  int outsample = 0;

  FILE * of = fopen(outfile, "a");
  if(of == NULL) {
    perror("open");
    fprintf(stderr, "Cannot open %s for writing\n", outfile);
    return 0;
  }

  for(i = *firpos; i<nsamples; i+=decim) {
    lv_32fc_t prod;

    volk_32fc_32f_dot_prod_32fc(&prod, (lv_32fc_t*) (alldata+i*COMPLEX), taps, tapslen/sizeof(float));

    fwrite(&prod, sizeof(lv_32fc_t), 1, of);

    outsample++;
  }

  *firpos = i - nsamples;

  fclose(of);

  return 0;

}

