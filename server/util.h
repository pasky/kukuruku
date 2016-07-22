#pragma once
#ifndef UTIL_H
#define UTIL_H

#include <err.h>
#include <volk/volk.h>

ssize_t readn(int, void *, int);
ssize_t writen(int, void *, int);

void* safe_malloc(size_t size);
void* volk_safe_malloc(size_t size, size_t align);
void* fftwf_safe_malloc(size_t size);

#endif
