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

blacklistfile = os.path.join(os.path.expanduser('~'), ".kukuruku/scanner/")
blacklistfile = os.path.join(blacklistfile, "blacklist.conf")

archdir = "archive"

if not os.path.isdir(archdir):
  os.mkdir(archdir)

if len(sys.argv) > 1:
  filenames = sys.argv[1:]
else:
  filenames = os.listdir(".")

for filename in filenames:

  fn = os.path.basename(filename)

  if fn[-6:] != ".cfile":
    continue

  p = fn.split("-")
  if len(p) != 8:
    continue

  p2 = p[7].split(".")

  rate = float(p2[0])
  freq = int(p[0])

  while True:
    print("Filename: %s | bandwidth %ik"%(filename, rate/1000))
    for i in range(0, len(modes)):
      print("%i) demod with %s"%(i, modes[modes.keys()[i]].name))
    print("d_) delete")
    print("a_) archive")
    print("_n) ignore once")
    print("_s) ignore by sorter (directly archive)")
    print("_h) ignore by scanner")
    print("q) just quit")
    c = raw_input('Choice: __ [optional comment] ')

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
      process.wait()

    elif c[0] == "q":
      sys.exit(0)
    elif len(c) >= 2:
      if c[0] == "d":
        os.remove(filename)
      elif c[0] == "a":
        os.rename(filename, archdir + "/" + filename)

      if c[1] == "s":
        bl = open(blacklistfile, "a")
        bl.write("i %i %i %s\n"%(freq, rate, c[3:]))
        bl.close()
      elif c[1] == "h":
        bl = open(blacklistfile, "a")
        bl.write("h %i %i %s\n"%(freq, rate, c[3:]))
        bl.close()

      break

    else:
      print("unknown input %s"%c)


