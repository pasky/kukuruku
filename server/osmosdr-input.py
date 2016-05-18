#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from __future__ import print_function

from gnuradio import blocks
from gnuradio import eng_notation
from gnuradio import gr
from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
import sys
import osmosdr
import time
import threading
import struct
import getopt

class top_block(gr.top_block):

  def __init__(self, device, rate, freq, gain, outpipe):
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
      
    self.blocks_file_sink = blocks.file_sink(gr.sizeof_gr_complex, outpipe, False)
    self.blocks_file_sink.set_unbuffered(False)

    self.connect((self.osmosdr_source, 0), (self.blocks_file_sink, 0))    

class sdr_iface():
  TUNE = 1
  PPM = 2
  GAIN = 3

tb = None
def set_param_thr(pipe, sdr):
  f = open(pipe, "rb")
  while True:
    ptype = struct.unpack("=B", f.read(1))[0]

    if ptype == sdr_iface.TUNE:
      data = f.read(8)
      freq = struct.unpack("=q", data)[0]

      print("tune %i"%freq)
      sdr.osmosdr_source.set_center_freq(freq, 0)
    elif ptype == sdr_iface.PPM:
      data = f.read(4)
      ppm = struct.unpack("=i", data)[0]

      print("ppm %i"%ppm)
      sdr.osmosdr_source.set_freq_corr(ppm, 0)
    elif ptype == sdr_iface.GAIN:
      fmt = "=4i"
      data = f.read(struct.calcsize(fmt))
      (auto, glo, interm, bb) = struct.unpack(fmt, data)

      if auto == 0:
        sdr.osmosdr_source.set_gain_mode(False, 0)
      else:
        sdr.osmosdr_source.set_gain_mode(True, 0)

      sdr.osmosdr_source.set_gain(glo, 0)
      sdr.osmosdr_source.set_if_gain(interm, 0)
      sdr.osmosdr_source.set_bb_gain(bb, 0)
    else:
      print("unknown type %i"%ptype)

def usage():
  print("Usage: %s -d device -r rate -i inpipe -o outfile -f freq -g gain"%(sys.argv[0]))
  sys.exit(2)

(device, rate, inpipe, outpipe) = [None]*4

try:
  (opts, args) = getopt.getopt(sys.argv[1:], "d:r:p:i:o:f:g:")
except getopt.GetoptError as e:
  usage()

for opt, arg in opts:
  if opt == "-d":
    device = arg
  elif opt == "-r":
    rate = arg
  elif opt == "-i":
    inpipe = arg
  elif opt == "-o":
    outpipe = arg
  elif opt == "-g":
    gain = arg
  elif opt == "-f":
    freq = arg
  elif opt == "-p":
    ppm = arg
  else:
    usage()
    assert False

if (not device) or (not rate) or (not inpipe) or (not outpipe) or \
   (not gain) or (not freq) or (not ppm):
  usage()

tb = top_block(device, rate, freq, gain, outpipe)

t = threading.Thread(target=set_param_thr, args=(inpipe, tb))
t.daemon = True
t.start()

tb.start()
try:
    raw_input('Press Enter to quit: ')
except EOFError:
    pass
tb.stop()
tb.wait()

