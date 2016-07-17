from __future__ import print_function

import os
import sys
import time
import threading
import getopt
import util
import hashlib
import math
import numpy as np
import xlater
import struct
import subprocess
import bisect
from datetime import datetime
from libutil import Struct, safe_cast

from gnuradio.filter import firdes

def channelhelper():
  ChannelHelperT = Struct("channelhelper", "rotator decim rate file taps carry rotpos firpos cylen fd_r")
  return ChannelHelperT()

COMPLEX64 = 8

class scanner():

  def __init__(self, l, confdir):
    self.l = l
    self.conf = util.ConfReader(confdir)

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
    self.l.l("%s -> %s"%(s, ret), "DBG")
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
    peaks = []
    for channel in cronframe.channels:
      peaks.append((channel.freq-cronframe.freq, channel.bw, channel))

    self.do_record(peaks, cronframe.cronlen, cronframe.stickactivity, 1, channel.freq, cronframe.floor, None)

  def scan(self, scanframe):
    ''' Find peaks in spectrum, record if specified in allow/blacklist '''
    starttime = time.time()
    self.sdr.tune(scanframe.freq)
    self.sdrflush()
    self.l.l("scan: tune %ik"%(scanframe.freq/1000), "INFO")

    delta = self.conf.interval - time.time() % self.conf.interval
    nbytes = int(self.conf.rate * COMPLEX64 * delta)
    nbytes -= nbytes % COMPLEX64
    sbuf = self.pipefile.read(nbytes)

    acc = self.compute_spectrum(sbuf)

    floor = sorted(acc)[int(scanframe.floor * self.conf.fftw)]

    peaks = self.find_peaks(acc, floor + scanframe.sql)

    peaks = self.filter_blacklist(peaks, scanframe.freq)

    self.do_record(peaks, scanframe.stick, scanframe.stickactivity, self.conf.filtermargin, scanframe.freq, scanframe.floor, sbuf)

  def filter_blacklist(self, peaks, center):
    ret = []
    for peak in peaks:
      f = peak[0]+center-peak[1]/2
      print(self.conf.blacklist)
      pos = bisect.bisect(self.conf.blacklist, f)

      if pos >= len(self.conf.blacklist):
        ret.append(peak)
        continue

      entry = self.conf.blacklist[pos]
      if entry-f > peak[1]:
        ret.append(peak)
        continue

      self.l.l("Removing blacklisted signal %i"%(peak[0]+center), "INFO")

    return ret

  def do_record(self, peaks, stoptime, stickactivity, safetymargin, center, floor, buf):

    lastact = time.time()

    helpers = []
    for peak in peaks:
      ch = channelhelper()

      f = peak[0]
      w = peak[1]*safetymargin

      ch.decim = math.ceil(self.conf.rate/w)
      ch.rate = self.conf.rate/ch.decim
      ch.rotator = -float(f)/self.conf.rate * 2*math.pi
      ch.rotpos = np.zeros(2, dtype=np.float32)
      ch.rotpos[0] = 1 # start with unit vector
      taps = firdes.low_pass(1, self.conf.rate, w/2, w*self.conf.transition, firdes.WIN_HAMMING)
      ch.taps = struct.pack("=%if"%len(taps), *taps)
      ch.firpos = np.zeros(1, dtype=np.int32)
      ch.cylen = len(ch.taps)
      ch.carry = '\0' * ch.cylen

      if len(peak) >= 3 and peak[2].pipe is not None:
        (ch.fd_r, ch.file) = os.pipe()
        subprocess.Popen([peak[2].pipe], shell=True, stdin=ch.fd_r, bufsize=-1)
        self.l.l("Recording %i (PIPE)"%f, "INFO")
      else:
        ch.file = os.open(self.getfn(f+center, ch.rate) + ".cfile", os.O_WRONLY|os.O_CREAT)
        self.l.l("Recording %s"%ch.file, "INFO")

      helpers.append(ch)

    while True:

      if buf is None:
        # read data from sdr
        buf = self.pipefile.read(self.conf.bufsize * COMPLEX64)

      # xlate each channel
      for ch in helpers:
        # ta vec s carry je nesmysl, udelal bych workery a ty by to zjistovaly podle ch.file
        xlater.xdump(buf, len(buf), ch.carry, ch.cylen, ch.taps, len(ch.taps),
                     int(ch.decim), ch.rotator, ch.rotpos, ch.firpos, ch.file)
        ch.carry = buf[-ch.cylen:]

      if stickactivity:
        acc = self.compute_spectrum(buf)
        for peak in peaks:
          if self.check_activity(acc, peak, floor):
            lastact = time.time()
            self.l.l("%f has activity, continuing"%peak[0], "INFO")

      if time.time() > lastact + stoptime:
        self.l.l("Record stop", "INFO")
        break

      buf = None

    for ch in helpers:
      os.close(ch.file)
      if ch.fd_r:
        os.close(ch.fd_r)

  def check_activity(self, acc, peak, q):
    floor = sorted(acc)[int(q * self.conf.fftw)]

    binhz = self.conf.rate/self.conf.fftw    

    startbin = int(peak[0]/binhz - peak[1]/(2*binhz))
    stopbin  = int(peak[0]/binhz + peak[1]/(2*binhz))

    for i in range(startbin, stopbin):
      if acc[i] > floor:
        return True

    return False

  def compute_spectrum(self, sbuf):

    acc = np.zeros(self.conf.fftw)
    iters = 0
    dt = np.dtype("=c8")
    for i in range(0, len(sbuf)-self.conf.fftw*COMPLEX64, self.conf.fftw*self.conf.fftskip*COMPLEX64): # compute short-time FFTs, sum result to acc
      buf = np.frombuffer(sbuf, count=self.conf.fftw, dtype=dt, offset = i)

      buf = buf*self.window

      fft = np.absolute(np.fft.fft(buf))

      acc += fft
      iters += 1

    acc = np.divide(acc, iters)
    acc = np.log(acc)

    # FFT yields a list of positive frequencies and then negative frequencies.
    # We want it in the "natural" order.
    acc = acc.tolist()[len(acc)/2:] + acc.tolist()[:len(acc)/2]

    # smooth the result with a simple triangular filter
    acc2 = [acc[0]]

    for i in range(1, len(acc)-1):
      acc2.append((acc[i-1]*0.5 + acc[i] + acc[i+1]*0.5) / 2)

    acc2.append(acc[len(acc)-1])

    return acc2

  def find_peaks(self, acc, floor):
    first = -1

    binhz = self.conf.rate/self.conf.fftw

    minspan = self.conf.minw/binhz
    maxspan = self.conf.maxw/binhz

    peaks = []

    for i in range(1, len(acc)):
      if acc[i] > floor and acc[i-1] < floor:
        first = i
      if acc[i] < floor and acc[i-1] > floor:
        if (i-first) >= minspan and (i-first) <= maxspan:
          f = binhz*(((i+first)/2)-self.conf.fftw/2)
          w = binhz*(i-first)
          peaks.append((f, w))
          self.l.l("signal at %f width %f"%(f, w), "INFO")

    return peaks

  def sdrflush(self):
    self.pipefile.read(self.conf.bufsize * COMPLEX64)

  def work(self, sdr, file_r):
    self.sdr = sdr
    self.pipefile = file_r

    self.window = np.hamming(self.conf.fftw)
    selframe = None
    reclen = None
    while(True):
      delta = self.conf.interval - time.time() % self.conf.interval
      if delta < self.conf.skip:
        time.sleep(delta)

      selframe = self.find_cronjob(self.conf.cronframes)

      if selframe:
        self.record_long(selframe)
        continue

      if len(self.conf.scanframes) > 0:
        # no cron job now -- pick some frame at random
        ctime = "%i"%(math.floor(time.time()) / self.conf.interval)
        idx = int(hashlib.sha256(self.conf.nonce + ctime).hexdigest(), 16) % len(self.conf.scanframes)
        scanframe = self.conf.scanframes[idx]
        self.scan(scanframe)
      else:
        time.sleep(delta)

