from __future__ import print_function

import sys
import time
import threading
import getopt
import util
import hashlib
import math
import numpy as np
import xlater
from datetime import datetime
from libutil import Struct, safe_cast

def channelhelper():
  ChannelHelperT = Struct("channelhelper", "rotator decim rate file taps carry rotpos firpos cylen")
  return ChannelHelperT(0.0, 0, 0, [])

COMPLEX64 = 8

class scanner():

  def __init__(self, l, sdr):
    self.l = l
    self.sdr = sdr

  def croncmp(self, i, frag):
    if frag == "*":
      return True
    if frag[:2] == "*/":
      num = safe_cast(frag[2:], int, None)
      if not num:
        self.l.l("Invalid modulo number %s"%frag[2:], "CRIT")
        return False
      if i % num == 0:
        return True
    raw = safe_cast(frag, int, None)
    if raw is not None:
      if raw == i:
        return True
    return False

  def crontest(self, s):
    pieces = s.split(" ")
    if len(pieces) != 5:
      self.l.l("malformed cron string %s"%s, "CRIT")
      return False

    d = datetime.fromtimestamp(time.time())

    ret = self.croncmp(d.minute, pieces[0]) and self.croncmp(d.hour, pieces[1]) and\
          self.croncmp(d.day, pieces[2]) and self.croncmp(d.month, pieces[3]) and\
          self.croncmp(d.weekday() + 1, pieces[4])
    self.l.l("%s -> %s"%(s, ret))
    return ret

  def find_cronjob(self, cronframes):
    for frame in cronframes:
      if self.crontest(frame.cron):
        return frame

  def getfn(self, f, rate):
    ds = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
    return "%i-%s-%i"%(f, ds, rate)

  def record_long(self, cronframe):
    ''' Record selected channels from a scheduled scan '''
    starttime = time.time()
    self.sdr.tune(cronframe.freq)
    self.l.l("cron record: tune %i"%cronframe.freq, "INFO")
    self.sdrflush()
    helpers = []
    for channel in cronframe.channels:
      ch = channelhelper()
      ch.decim = math.ceil(self.samplerate / channel.bw)
      ch.rate = self.samplerate/ch.decim
      ch.file = self.getfn(channel.freq, ch.rate) + ".cfile"
      ch.rotator = -float(channel.freq-cronframe.freq)/self.samplerate * 2*math.pi
      ch.rotpos = np.zeros(2, dtype=np.float32)
      ch.rotpos[0] = 1 # start with unit vector
      ch.taps = channel.taps
      ch.firpos = np.zeros(1, dtype=np.int32)
      ch.cylen = len(ch.taps)
      ch.carry = '\0' * ch.cylen
      helpers.append(ch)

    while True:
      if time.time() - starttime > cronframe.cronlen:
        for ch in helpers:
          ch.file.close()
        return

      # read data from sdr
      buf = self.pipefile.read(self.conf.bufsize * COMPLEX64)

      print("read %i of %i"%(len(buf), self.conf.bufsize))

      # xlate each channel
      for ch in helpers:
        xlater.xdump(buf, len(buf), ch.carry, ch.cylen, ch.taps, len(ch.taps),
                     int(ch.decim), ch.rotator, ch.rotpos, ch.firpos, ch.file)
        ch.carry = buf[-ch.cylen:]

  def scan(self, scanframe):
    ''' Find peaks in spectrum, record if specified in allow/blacklist '''
    starttime = time.time()
    self.sdr.tune(scanframe.freq)
    self.sdrflush()
    self.l.l("scan: tune %i"%scanframe.freq, "INFO")
    time.sleep(10)

  def sdrflush(self):
    self.pipefile.read(self.conf.bufsize * COMPLEX64)

  def work(self, confdir, outpipe):
    self.samplerate = self.sdr.get_sample_rate()
    self.pipefile = open(outpipe, "rb")

    self.conf = util.ConfReader(confdir, self.samplerate)

    selframe = None
    reclen = None
    while(True):
      selframe = self.find_cronjob(self.conf.cronframes)

      if selframe:
        self.record_long(selframe)
        continue

      # no cron job now -- pick some frame at random
      ctime = "%i"%(math.floor(time.time()) / self.conf.interval)
      idx = int(hashlib.sha256(self.conf.nonce + ctime).hexdigest(), 16) % len(self.conf.scanframes)
      scanframe = self.conf.scanframes[idx]
      self.scan(scanframe)

