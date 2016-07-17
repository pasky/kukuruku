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

  def __init__(self, device, rate, freq, gain, fd):
    self.rate = rate
    self.gain = gain

    gr.top_block.__init__(self, "Top Block")

    self.osmosdr_source = osmosdr.source(device)
    self.osmosdr_source.set_sample_rate(int(rate))
    self.osmosdr_source.set_center_freq(int(freq), 0)
    self.osmosdr_source.set_freq_corr(0, 0)
    self.osmosdr_source.set_dc_offset_mode(0, 0)
    self.osmosdr_source.set_iq_balance_mode(2, 0)
    self.osmosdr_source.set_gain_mode(False, 0)
    self.osmosdr_source.set_gain(int(gain), 0)
    self.osmosdr_source.set_if_gain(int(gain), 0)
    self.osmosdr_source.set_bb_gain(int(gain), 0)
    self.osmosdr_source.set_antenna("", 0)
    self.osmosdr_source.set_bandwidth(0, 0)
      
    self.blocks_file_descriptor_sink_0 = blocks.file_descriptor_sink(gr.sizeof_float*2, fd)

    self.connect((self.osmosdr_source, 0), (self.blocks_file_descriptor_sink_0, 0))

  # osmosdr.source.get_sample_rate() seems to be broken
  def get_sample_rate(self):
    return self.rate

  def tune(self, f):
    self.osmosdr_source.set_center_freq(int(f), 0)

import KukurukuScanner
import util

def usage():
  print("Usage: %s [-d device] [-p ppm] [-r rate] -c confdir"%sys.argv[0])
  sys.exit(1)

ppm = 0
device = ""
rate = 2048000
confdir = None

try:
  (opts, args) = getopt.getopt(sys.argv[1:], "d:r:p:c:")
except getopt.GetoptError as e:
  usage()

for opt, arg in opts:
  if opt == "-d":
    device = arg
  elif opt == "-r":
    rate = arg
  elif opt == "-c":
    confdir = arg
  elif opt == "-p":
    ppm = arg
  else:
    usage()
    assert False

if not confdir:
  usage()

(fd_r,fd_w) = os.pipe()

sdr = top_block(device, rate, 0, 10, fd_w)

l = util.logger()
l.setloglevel("DBG")

scanner = KukurukuScanner.scanner(l, confdir)

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
