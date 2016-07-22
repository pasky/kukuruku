#pragma once
#ifndef XLATE_WORKER_H
#define XLATE_WORKER_H

#include "worker.h"
worker * create_xlate_worker(float, int, int, float *, int);
void * xlate_worker_thr(void *);

#endif
