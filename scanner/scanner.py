#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from __future__ import print_function

from gnuradio import blocks
from gnuradio import eng_notation
from gnuradio import gr
from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
import sys
import os
import osmosdr
import time
import threading
import getopt
import tempfile

class top_block(gr.top_block):

  def __init__(self, device, rate, ppm, fd):
    self.rate = rate

    gr.top_block.__init__(self, "Top Block")

    self.osmosdr_source = osmosdr.source(device)
    self.osmosdr_source.set_sample_rate(int(rate))
    self.osmosdr_source.set_freq_corr(ppm, 0)
    self.osmosdr_source.set_dc_offset_mode(0, 0)
    self.osmosdr_source.set_iq_balance_mode(2, 0)
    self.osmosdr_source.set_antenna("", 0)
    #self.osmosdr_source.set_bandwidth(0, 0)
      
    self.blocks_file_descriptor_sink_0 = blocks.file_descriptor_sink(gr.sizeof_float*2, fd)

    self.connect((self.osmosdr_source, 0), (self.blocks_file_descriptor_sink_0, 0))

  # osmosdr.source.get_sample_rate() seems to be broken
  def get_sample_rate(self):
    return self.rate

  def tune(self, f):
    self.osmosdr_source.set_center_freq(int(f), 0)

  def set_gain(self, pos, val):
    if pos == 0:
      self.osmosdr_source.set_gain_mode((val != 0), 0)
    elif pos == 1:
      self.osmosdr_source.set_gain(val, 0)
    elif pos == 2:
      self.osmosdr_source.set_if_gain(val, 0)
    elif pos == 3:
      self.osmosdr_source.set_bb_gain(val, 0)
    else:
      raise Exceprion("Invalid gain number %s"%val)

from KukurukuScanner import KukurukuScanner
import util

def usage():
  print("Usage: %s [-d device] [-p ppm] [-r rate] -c confdir"%sys.argv[0])
  sys.exit(1)

ppm = 0
device = ""
confdir = None

try:
  (opts, args) = getopt.getopt(sys.argv[1:], "d:c:p:")
except getopt.GetoptError as e:
  usage()

ppm = 0
device = ""
for opt, arg in opts:
  if opt == "-d":
    device = arg
  elif opt == "-c":
    confdir = arg
  elif opt == "-p":
    ppm = arg
  else:
    usage()
    assert False

if not confdir:
  usage()

l = util.logger()
l.setloglevel("DBG")

(fd_r,fd_w) = os.pipe()

scanner = KukurukuScanner(l, confdir)

sdr = top_block(device, scanner.conf.rate, ppm, fd_w)

for i in range(0, 4):
  sdr.set_gain(i, int(scanner.conf.gainpcs[i]))

file_r = os.fdopen(fd_r, "rb")

t = threading.Thread(target=scanner.work, args = (sdr,file_r))
t.daemon = True
t.start()

sdr.start()

try:
  raw_input('Press Enter to quit: ')
except EOFError:
  pass
sdr.stop()
