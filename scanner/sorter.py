#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import subprocess
import time

from ConfReader import ConfReader, read_modes

conf = ConfReader(os.getenv('HOME') + '/.kukuruku/gui')
modes = read_modes(os.getenv('HOME') + '/.kukuruku/modes')

archdir = "archive"

if not os.path.isdir(archdir):
  os.mkdir(archdir)

filenames = os.listdir(".")

for filename in filenames:
  if filename[-6:] != ".cfile":
    continue

  p = filename.split("-")
  if len(p) != 8:
    continue

  p2 = p[7].split(".")

  rate = float(p2[0])

  while True:
    print("Filename: %s | bandwidth %ik"%(filename, rate/1000))
    for i in range(0, len(modes)):
      print("%i) demod with %s"%(i, modes[modes.keys()[i]].name))
    print("d_) delete")
    print("a_) archive")
    print("_n) ignore once")
    print("_s) ignore by sorter")
    print("_h) ignore by scanner")
    c = raw_input('Choice: __ [optional comment]')

    if c.isdigit():
      modename = modes.keys()[int(c)]

      resample = float(rate) / modes[modename].rate

      if rate != modes[modename].rate and not modes[modename].resample:
        print("Channel samplerate %i must be an integer multiple of module samplerate %i!"%(samplerate, modes[mode].rate))
        continue

      program = modes[modename].program.replace("_MODEPATH_", conf.modepath)
      if rate != modes[modename].rate:
        print("resample ratio = %f"%resample)
        program += " -r %f"%resample
      process = subprocess.Popen(["cat " + filename + " | " + program], shell=True)
    elif len(c) >= 2:
      if c[0] == "d":
        os.remove(filename)
      elif c[0] == "a":
        os.remane(filename, archdir + "/" + filename)

      if c[1] == "s":
        pass
      elif c[1] == "h":
        pass






