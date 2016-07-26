# -*- coding: utf-8 -*-

from __future__ import print_function

import configparser
import os
import sys
from framespec import scanframe, cronframe, channel
import math
from threading import Lock
from datetime import datetime
import time
from gnuradio.filter import firdes
import struct

from libutil import cfg_safe, engnum

MAINSECTION = "General"

class ConfReader():
  def __init__(self):

    confdir = os.path.join(os.path.expanduser('~'), ".kukuruku/scanner/")

    # Read global config
    rc = configparser.ConfigParser()
    cfpath = os.path.join(confdir, "main.conf")
    rc.read(cfpath)

    self.bufsize = cfg_safe(rc.getint, MAINSECTION, 'bufsize', 2048000, cfpath)
    self.rate = cfg_safe(rc.getint, MAINSECTION, 'rate', 2048000, cfpath)
    self.interval = cfg_safe(rc.getint, MAINSECTION, 'interval', 5, cfpath)
    self.skip = cfg_safe(rc.getint, MAINSECTION, 'skip', 3, cfpath)
    self.fftw = cfg_safe(rc.getint, MAINSECTION, 'fftw', 2048, cfpath)
    self.fftskip = cfg_safe(rc.getint, MAINSECTION, 'fftskip', 32, cfpath)
    self.overlap = cfg_safe(rc.getfloat, MAINSECTION, 'overlap', 0.2, cfpath)
    self.nonce = cfg_safe(rc.get, MAINSECTION, 'nonce', "abcdef", cfpath)
    self.floor = cfg_safe(rc.getfloat, MAINSECTION, 'floor', 0.4, cfpath)
    self.sql = cfg_safe(rc.getfloat, MAINSECTION, 'sql', 0.5, cfpath)
    self.filtermargin = cfg_safe(rc.getfloat, MAINSECTION, 'filtermargin', 1.5, cfpath)
    self.transition = cfg_safe(rc.getfloat, MAINSECTION, 'transition', 0.2, cfpath)
    self.minw = cfg_safe(rc.get, MAINSECTION, 'minw', 10000, cfpath)
    self.maxw = cfg_safe(rc.get, MAINSECTION, 'maxw', 200000, cfpath)
    self.messgain = cfg_safe(rc.getint, MAINSECTION, 'messgain', 1, cfpath)
    self.mingain = cfg_safe(rc.getint, MAINSECTION, 'mingain', 10, cfpath)
    self.maxgain = cfg_safe(rc.getint, MAINSECTION, 'maxgain', 49, cfpath)
    self.gain = cfg_safe(rc.get, MAINSECTION, 'gain', "0,30,30,30", cfpath)
    self.stickactivity = cfg_safe(rc.getboolean, MAINSECTION, 'stickactivity', False, cfpath)
    self.stick = cfg_safe(rc.getint, MAINSECTION, 'stick', 10, cfpath)
    self.silencegap = cfg_safe(rc.getint, MAINSECTION, 'silencegap', 5, cfpath)
    self.dumpspectrum = cfg_safe(rc.get, MAINSECTION, 'dumpspectrum', "never", cfpath)

    self.gainpcs = self.gain.split(",")
    if len(self.gainpcs) != 4:
      print("Wrong gain string format in configuration %s, should be \"N,N,N,N\""%self.gain)
      sys.exit(1)
    if self.messgain < -1 or self.messgain > 3:
      print("messagin parameter must be an integer from range [-1, 3]")
      sys.exit(1)

    defaultgain = int(self.gainpcs[self.messgain])

    self.minw = engnum(self.minw)
    self.maxw = engnum(self.maxw)
    self.rate = engnum(self.rate)

    files = [f for f in os.listdir(confdir) if os.path.isfile(os.path.join(confdir, f))]

    self.scanframes = []
    self.cronframes = []

    step = float(self.rate) * (1.0-self.overlap)

    # Read scanframe and channel config files
    for f in files:
      if f == "main.conf" or f == "blacklist.conf":
        continue
      if f[-5:] != ".conf":
        continue

      print("file %s"%f)

      rc = configparser.ConfigParser()
      rc.read(os.path.join(confdir, f))

      floor = cfg_safe(rc.getfloat, MAINSECTION, 'floor', self.floor)
      sql = cfg_safe(rc.getfloat, MAINSECTION, 'sql', self.sql)
      stickactivity = cfg_safe(rc.getboolean, MAINSECTION, 'stickactivity', self.stickactivity)
      stick = cfg_safe(rc.getfloat, MAINSECTION, 'stick', self.stick)
      silencegap = cfg_safe(rc.getfloat, MAINSECTION, 'silencegap', self.silencegap)

      if "freqstart" in rc.options(MAINSECTION): # range randscan
        freqstart = rc.get(MAINSECTION, "freqstart")
        freqstart = engnum(freqstart) + step/2

        freqstop = rc.get(MAINSECTION, "freqstop")
        freqstop = engnum(freqstop) - step/2

        numf = int(math.ceil(float(freqstop - freqstart)/step))

        if numf == 0: # freqstart == freqstop
          numf = 1
          delta = freqstop
        else:
          delta = float(freqstop - freqstart) / numf
        cf = freqstart
        while cf <= math.ceil(freqstop):
          frm = scanframe()
          frm.freq = cf
          frm.floor = floor
          frm.stickactivity = stickactivity
          frm.stick = stick
          frm.silencegap = silencegap
          frm.sql = sql
          frm.gain = defaultgain

          self.scanframes.append(frm)
          print("insert %f"%cf)
          cf += math.floor(delta)
      elif "cron" in rc.options(MAINSECTION): # scheduled recording
        channels = self.channel_list_from_config(rc)

        frm = cronframe()
        frm.freq = engnum(rc.get(MAINSECTION, "freq"))
        frm.floor = self.floor
        frm.stickactivity = stickactivity
        frm.stick = stick
        frm.silencegap = silencegap
        frm.sql = sql
        frm.gain = defaultgain
        frm.cron = rc.get(MAINSECTION, "cron")
        frm.channels = channels

        self.cronframes.append(frm)

      randscan = cfg_safe(rc.getboolean, MAINSECTION, "randscan", True)

      if ((not ("freqstart" in rc.options(MAINSECTION))) and randscan):
        frm = scanframe()
        frm.freq = engnum(rc.get(MAINSECTION, "freq"))
        frm.floor = floor
        frm.stickactivity = stickactivity
        frm.stick = stick
        frm.silencegap = silencegap
        frm.sql = sql
        frm.gain = defaultgain

        channels = self.channel_list_from_config(rc)
        frm.channels = channels

        self.scanframes.append(frm)

    # read blacklist
    bl = []
    blpath = os.path.join(confdir, "blacklist.conf")
    if os.path.isfile(blpath):
      f = open(blpath)
      lines = f.readlines()
      for line in lines:
        pieces = line.strip().split(" ")
        if len(pieces) >= 3:
          if pieces[0] == "h":
            freq = int(pieces[1])
            bw = int(pieces[2])/2
            bl.append((freq-bw, freq+bw))

    self.blacklist = []
    if len(bl) > 0:
      # sort and union intervals
      bl.sort(key=lambda x: x[0])
      self.blacklist.append(bl[0])
      for interval in bl[1:]:
        if self.blacklist[-1][1] < interval[0]:
          self.blacklist.append(interval)
        elif self.blacklist[-1][1] == interval[0]:
          self.blacklist[-1][1] = interval[1]


  def channel_list_from_config(self, rc):
    channels = []
    for ssect in rc.sections():
      if ssect == MAINSECTION:
        continue

      ch = channel()
      ch.freq = engnum(rc.get(ssect, "freq"))
      ch.bw = engnum(rc.get(ssect, "bw"))
      taps = firdes.low_pass(1, self.rate, ch.bw, ch.bw*self.transition, firdes.WIN_HAMMING)
      ch.taps = struct.pack("=%if"%len(taps), *taps)

      ch.pipe = cfg_safe(rc.get, ssect, 'pipe', None)

      channels.append(ch)

    return channels


class logger():

  def __init__(self):
    self.loglevel = -1
    self.loglevels = ["DBG", "INFO", "WARN", "CRIT"]

    self.loglock = Lock()

    self.PURPLE = '\033[95m'
    self.BLUE = '\033[96m'
    self.GREEN = '\033[92m'
    self.YELLOW = '\033[93m'
    self.RED = '\033[91m'
    self.ENDC = '\033[0m'
    self.BOLD = '\033[1m'
    self.UNDERLINE = '\033[4m'

  def setloglevel(self, l):
    self.loglevel = self.loglevels.index(l)

  def l(self, s, level="INFO"):
    """ Logging function. Params: message, loglevel. """

    if self.loglevels.index(level) < self.loglevel:
      return

    self.loglock.acquire()

    if level == "DBG":
      print(self.PURPLE, end="")
    elif level == "INFO":
      print(self.BLUE, end="")
    elif level == "WARN":
      print(self.YELLOW, end="")
    elif level == "CRIT":
      print(self.RED, end="")

    print(datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S '), end="")

    print(s)

    print(self.ENDC, end="")

    self.loglock.release()


