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

class KukurukuScanner():

  def __init__(self, l, confdir):
    self.l = l
    self.conf = util.ConfReader(confdir)

  def croncmp(self, i, frag):
    if frag == "*":
      return True
    if frag[:2] == "*/":
      num = safe_cast(frag[2:], int, None)
      if not num or num == 0:
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
    if rate is not None:
      return "%i-%s-%i"%(f, ds, rate)
    else:
      return "%i-%s"%(f, ds)

  def dump_spectrum(self, acc, filename):
    f = open(filename, "wb")
    for flt in acc:
      f.write("%f\n"%flt)
    f.close()

  def record_long(self, cronframe):
    ''' Record selected channels from a scheduled scan '''
    starttime = time.time()
    self.sdr.tune(cronframe.freq)
    self.l.l("cron record: tune %i"%cronframe.freq, "INFO")
    self.sdrflush()
    peaks = []
    for channel in cronframe.channels:
      peaks.append((channel.freq-cronframe.freq, channel.bw, channel))

    self.do_record(peaks, cronframe.cronlen, 1, None, cronframe)

  def scan(self, scanframe):
    ''' Find peaks in spectrum, record if specified in allow/blacklist '''
    starttime = time.time()
    self.sdr.tune(scanframe.freq)
    self.sdr.set_gain(self.conf.messgain, scanframe.gain)
    self.sdrflush()
    self.l.l("scan: tune %ik, gain %i"%(scanframe.freq/1000, scanframe.gain), "INFO")

    delta = self.conf.interval - time.time() % self.conf.interval
    nbytes = int(self.conf.rate * COMPLEX64 * delta)
    nbytes -= nbytes % COMPLEX64
    sbuf = self.pipefile.read(nbytes)

    acc = self.compute_spectrum(sbuf)

    if self.conf.dumpspectrum == "always":
      self.dump_spectrum(acc, self.getfn(scanframe.freq, None)+".spectrum.txt")

    floor = sorted(acc)[int(scanframe.floor * self.conf.fftw)]

    peaks = self.find_peaks(acc, floor + scanframe.sql)

    peaks = self.filter_blacklist(peaks, scanframe.freq)

    if len(peaks) == 0:
      histo = self.compute_histogram(sbuf[:COMPLEX64*self.conf.fftw])
      self.update_and_set_gain(scanframe, histo)
      self.sdr.set_gain(self.conf.messgain, scanframe.gain)
    else:
      if self.conf.dumpspectrum == "on_signal":
        self.dump_spectrum(acc, self.getfn(scanframe.freq, None)+".spectrum.txt")
      self.do_record(peaks, scanframe.stick, self.conf.filtermargin, sbuf, scanframe)

  def filter_blacklist(self, peaks, center):
    ret = []
    if not self.conf.blacklist:
      return peaks

    for peak in peaks:
      f = peak[0]+center

      pos = bisect.bisect(self.conf.blacklist, (f, None))

      if pos >= len(self.conf.blacklist):
        pos -= 1

      entry = self.conf.blacklist[pos]

      if f < entry[0] or f > entry[1]:
        ret.append(peak)
        continue

      self.l.l("Removing blacklisted signal %i"%(peak[0]+center), "INFO")

    return ret

  def update_and_set_gain(self, frame, histo):
    diff = 0
    # if there is some signal in the highest 10 bins, decrease gain
    if sum(histo[-10:]) > 0:
      diff = -1
    # if there is no signal in the upper half, increase gain
    if sum(histo[-50:]) == 0:
      diff = 1

    frame.gain += diff
    frame.gain = np.clip(frame.gain, self.conf.mingain, self.conf.maxgain)

  def do_record(self, peaks, stoptime, safetymargin, buf, frame):

    lastact = time.time()
    center = frame.freq
    floor = frame.floor

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

      basename = self.getfn(f+center, ch.rate)
      if len(peak) >= 3 and peak[2].pipe is not None:
        (ch.fd_r, ch.file) = os.pipe()
        cmdline = peak[2].pipe.replace("_FILENAME_", basename)
        subprocess.Popen([cmdline], shell=True, stdin=ch.fd_r, bufsize=-1)
        self.l.l("Recording \"%s\" (PIPE), firlen %i"%(cmdline, len(taps)), "INFO")
      else:
        fullfile = basename + ".cfile"
        ch.file = os.open(fullfile, os.O_WRONLY|os.O_CREAT)
        ch.fd_r = None
        self.l.l("Recording to file \"%s\", firlen %i"%(fullfile, len(taps)), "INFO")

      helpers.append(ch)

    while True and len(helpers) > 0:

      # read data from sdr if needed
      if buf is None:
        buf = self.pipefile.read(self.conf.bufsize * COMPLEX64)
        if frame.stickactivity:
          acc = self.compute_spectrum(buf)
          for peak in peaks:
            if self.check_activity(acc, peak, floor):
              lastact = time.time()
              self.l.l("%f has activity, continuing"%peak[0], "INFO")

      # xlate each channel
      for ch in helpers:
        # ta vec s carry je nesmysl, udelal bych workery a ty by to zjistovaly podle ch.file
        xlater.xdump(buf, len(buf), ch.carry, ch.cylen, ch.taps, len(ch.taps),
                     int(ch.decim), ch.rotator, ch.rotpos, ch.firpos, ch.file)
        ch.carry = buf[-ch.cylen:]

      if time.time() > lastact + stoptime:
        self.l.l("Record stop", "INFO")
        break

      histo = self.compute_histogram(buf[:COMPLEX64*self.conf.fftw])
      self.update_and_set_gain(frame, histo)
      self.sdr.set_gain(self.conf.messgain, frame.gain)

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

  def compute_histogram(self, sbuf):
    """ Compute histogram with 100 bins """
    acc = np.zeros(100)
    dt = np.dtype("=f4")
    buf = np.frombuffer(sbuf, dtype=dt)
    for i in range(0, len(buf)):
      acc[np.clip(int(buf[i]*99), 0, 99)] += 1
    return acc

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

