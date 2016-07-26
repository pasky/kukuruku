#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import libclient
import time
import math
from gnuradio.filter import firdes

# Create client object
cl = libclient.client()

rid = None
wid = None

# This gets called every time xlaters dictionary is changed
def xlater_cb():
  global rid, wid
  xls = cl.get_xlaters()
  # go through the dictionary and look for our xlater
  for w in xls:
    r = xls[w].rid
    if r == rid:
      # if found, put the server-assigned ID to wid
      wid = w

cl.set_xlater_callback(xlater_cb)

cl.connect("localhost", 4444)

cl.set_auto_enable_xlater(True)

# compute rotator for -300 kHz
# a more portable implementation would register info_callback and use the server-provided samplerate
rotate = 300000.0/2048000 * 2*math.pi
# this is coarse too, kukuruku-gui uses fractional resampling
decim = 2048000/48000

# create the xlater, the temporary remote ID gets stored in rid
rid = cl.create_xlater(rotate, decim, firdes.low_pass(1, 2048000, 20000, 10000, firdes.WIN_HAMMING), "./modes/mfm.py", -1)
print "Created xlater, reference %i"%rid

# wait for 10 s and if we have the server-assigned ID, retune to some other frequency
time.sleep(10)
if wid is not None:
  print("retune")
  rotate = 700000.0/2048000 * 2*math.pi
  cl.modify_xlater(wid, rotate, None)
  time.sleep(10)

# and kill the whole chain
print("destroy")
cl.disable_xlater(wid)
cl.destroy_xlater(wid)

cl.disconnect()
