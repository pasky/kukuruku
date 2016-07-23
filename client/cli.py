#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import libclient
import time
from gnuradio.filter import firdes

cl = libclient.client()

rid = None
wid = None

def xlater_cb():
  global rid, wid
  xls = cl.get_xlaters()
  for w in xls:
    r = xls[w].rid
    if r == rid:
      wid = w

cl.set_xlater_callback(xlater_cb)

cl.connect("localhost", 4444)

cl.set_auto_enable_xlater(True)
rid = cl.create_xlater(0.92, 43, firdes.low_pass(1, 2048000, 20000, 5000, firdes.WIN_HAMMING), "./modes/mfm.py", -1)
print "Created xlater, reference %i"%rid

time.sleep(5)
if wid is not None:
  print("retune")
  cl.modify_xlater(wid, 2.15, firdes.low_pass(1, 2048000, 20000, 5000, firdes.WIN_HAMMING))
  time.sleep(5)
  print("destroy")
  cl.disable_xlater(wid)
  cl.destroy_xlater(wid)

cl.disconnect()
