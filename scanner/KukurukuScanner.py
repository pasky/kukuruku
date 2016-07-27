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
  """ channelhelper is created when we are recording a channel.
      np.complex64 ch.rotpos - vector denoting current rotator phase
      np.int32 ch.firpos - we start the filter evaluation at this sample
       (needed when frame length is not divisible by decimation)
      carry, cylen - buffer where part of the signal is stored and carried to the
       next iteration (we need it because the FIR filter needs to read samples from the history)
  """

  ChannelHelperT = Struct("channelhelper", "decim rate rotator rotpos firpos cylen carry")
  return ChannelHelperT()

def peak(freq, bw, pipe, archive):
  """ One peak that is to be recorded
      freq - frequency relative to the center frequency
      pipe - command to be executed (instead of saving samples to file, they are piped to a process)
      archive - whether to save to an archive/ directory or to a current directory
  """
  PeakT = Struct("peak", "freq bw pipe archive")
  return PeakT(freq, bw, pipe, archive)

# length in bytes
COMPLEX64 = 8

class KukurukuScanner():

  def __init__(self, l):
    self.l = l
    self.conf = util.ConfReader()

  def croncmp(self, i, frag):
    """ Compare cron field (e.g. "*", "15" or "*/5"), return True on positive match.
    i - number to compare with
    frag - the cron field
    """
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
    """ Test a cron string 's' (e.g. "*/5 * * * 1") against current time, return True on positive match. """
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
    """ Check cron string of all frames, return the first frame that matches or None """
    for frame in cronframes:
      if self.crontest(frame.cron):
        return frame

  def getfn(self, f, rate):
    """ Build filename from frequency, current date and channel rate """
    ds = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
    if rate is not None:
      return "%i-%s-%i"%(f, ds, rate)
    else:
      return "%i-%s"%(f, ds)

  def dump_spectrum(self, acc, filename):
    """ Write acc, which is an array of floats, to a file """
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
      peaks.append(peak(channel.freq-cronframe.freq, channel.bw, channel.pipe, True))

    self.do_record(peaks, None, cronframe)

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

      # determine whether we stumbled upon any specified channel which has PIPE set
      for peak in peaks:
        for channel in scanframe.channels:
          if channel.freq - scanframe.freq - channel.bw/2 < peak.freq and \
             channel.freq - scanframe.freq + channel.bw/2 > peak.freq:

            peak.freq = channel.freq - scanframe.freq
            peak.bw = channel.bw
            peak.pipe = channel.pipe
            peak.archive = True

      self.do_record(peaks, sbuf, scanframe)

  def find_in_interval_list(self, l, key):
    """ Bisect list "l" of intervals sorted by start points, return True if key is in some interval """

    if not l:
      return False

    pos = bisect.bisect(l, (key, None))

    if pos >= len(l):
      pos -= 1

    entry = l[pos]

    if key > entry[0] and key < entry[1]: # found
      return True

    return False

  def filter_blacklist(self, peaks, center):
    """ Transform peaks list:
     - remove peaks that have center frequency with "h" flag in blacklist
     - set archive = True to peaks that have "i" flag in blacklist

     parameters: peaks - peak list
     center - center frequency (because the peak has only relative frequency in it)
    """
    ret = []

    for peak in peaks:
      f = peak.freq+center

      if not self.find_in_interval_list(self.conf.blacklist, f):
        if self.find_in_interval_list(self.conf.archivelist, f):
          peak.archive = True
        ret.append(peak)
        continue

      self.l.l("Removing blacklisted signal %i"%(peak.freq+center), "INFO")

    return ret

  def update_and_set_gain(self, frame, histo):
    """ evaluate computed histogram and increase/decrease gain of frame accordingly """
    diff = 0
    # if there is some signal in the highest 10 bins, decrease gain
    if sum(histo[-10:]) > 0:
      diff = -1
    # if there is no signal in the upper half, increase gain
    if sum(histo[-50:]) == 0:
      diff = 1

    frame.gain += diff
    frame.gain = np.clip(frame.gain, self.conf.mingain, self.conf.maxgain)

  def do_record(self, peaks, buf, frame):
    """ Recort "peaks" to respective files or pipes. """

    lastact = time.time()
    center = frame.freq
    floor = frame.floor
    stoptime = time.time() + frame.stick

    helpers = []
    for peak in peaks:
      ch = channelhelper()

      f = peak.freq
      w = peak.bw

      ch.decim = math.ceil(self.conf.rate/w)
      ch.rate = self.conf.rate/ch.decim
      ch.rotator = -float(f)/self.conf.rate * 2*math.pi
      ch.rotpos = np.zeros(2, dtype=np.float32)
      ch.rotpos[0] = 1 # start with unit vector
      transition_band = w*self.conf.transition
      taps = firdes.low_pass(1, self.conf.rate, w/2-transition_band, transition_band, firdes.WIN_HAMMING)
      ch.taps = struct.pack("=%if"%len(taps), *taps)
      ch.firpos = np.zeros(1, dtype=np.int32)
      ch.cylen = len(ch.taps)
      ch.carry = '\0' * ch.cylen

      basename = self.getfn(f+center, ch.rate)

      if peak.pipe is not None:
        # spawn process, pipe to stdin
        (ch.fd_r, ch.file) = os.pipe()
        cmdline = peak.pipe.replace("_FILENAME_", basename)
        subprocess.Popen([cmdline], shell=True, stdin=ch.fd_r, bufsize=-1)
        self.l.l("Recording \"%s\" (PIPE), firlen %i"%(cmdline, len(taps)), "INFO")
      else:
        # write to file
        if peak.archive:
          basename = "archive/"+basename
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
            if self.check_activity(acc, peak, floor, frame.sql):
              lastact = time.time()
              self.l.l("%f has activity, continuing"%peak.freq, "INFO")

      # xlate each channel
      for ch in helpers:
        # ta vec s carry je nesmysl, udelal bych workery a ty by to zjistovaly podle ch.file
        xlater.xdump(buf, len(buf), ch.carry, ch.cylen, ch.taps, len(ch.taps),
                     int(ch.decim), ch.rotator, ch.rotpos, ch.firpos, ch.file)
        ch.carry = buf[-ch.cylen:]

      # check if we have either reached end specified by "stick" or
      #  there is no activity for at least "silencegap" seconds
      if ((not frame.stickactivity) and time.time() > stoptime) or \
        (frame.stickactivity and time.time() > lastact + frame.silencegap):
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

  def check_activity(self, acc, peak, q, sql):
    """ Check if a given peak is active
    acc - computed spectrum
    q - relevant percentile
    """
    floor = sorted(acc)[int(q * self.conf.fftw)] + sql

    binhz = self.conf.rate/self.conf.fftw    

    startbin = int(peak.freq/binhz - peak.bw/(2*binhz)) + self.conf.fftw/2
    stopbin  = int(peak.freq/binhz + peak.bw/(2*binhz)) + self.conf.fftw/2

    for i in range(startbin, stopbin):
      if acc[i] > floor:
        return True

    return False

  def compute_histogram(self, sbuf):
    """ Compute histogram with 100 bins (hardcoded for now) """
    acc = np.zeros(100)
    dt = np.dtype("=f4")
    buf = np.frombuffer(sbuf, dtype=dt)
    for i in range(0, len(buf)):
      acc[np.clip(int(buf[i]*99), 0, 99)] += 1
    return acc

  def compute_spectrum(self, sbuf):
    """ Compute power spectrum (10log_10((Re^2+Im^2)/N) of signal in buf. """

    acc = np.zeros(self.conf.fftw)
    iters = 0
    dt = np.dtype("=c8")
    for i in range(0, len(sbuf)-self.conf.fftw*COMPLEX64, self.conf.fftw*self.conf.fftskip*COMPLEX64): # compute short-time FFTs, sum result to acc
      buf = np.frombuffer(sbuf, count=self.conf.fftw, dtype=dt, offset = i)

      buf = buf*self.window

      fft = np.fft.fft(buf)
      fft = (np.real(fft) * np.real(fft) + np.imag(fft) * np.imag(fft))/self.conf.fftw
      fft = np.log10(fft)*10

      acc += fft
      iters += 1

    acc = np.divide(acc, iters)

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
    """ Find peaks in spectrum -- chunks that have power above floor """

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
          w = binhz*(i-first)*self.conf.filtermargin
          peaks.append(peak(f, w, None, False))
          self.l.l("signal at %f width %f"%(f, w), "INFO")

    return peaks

  def sdrflush(self):
    """ Read self.conf.bufsize samples to flush buffers in osmosdr """
    self.pipefile.read(self.conf.bufsize * COMPLEX64)

  def work(self, sdr, file_r):
    """ General work.
    sdr - gnuradio.gr.top_block object
    file_r - file object (opened pipe) to read samples from
    """
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

