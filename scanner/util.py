# -*- coding: utf-8 -*-

from __future__ import print_function

import configparser
import os
from framespec import scanframe, cronframe, channel
import math
from threading import Lock
from datetime import datetime
import time
from gnuradio.filter import firdes
import struct

MAINSECTION = "General"

class ConfReader():
  def __init__(self, path, samplerate):

    # Read global config
    rc = configparser.ConfigParser()
    rc.read(os.path.join(path, "main.conf"))
    self.bufsize = rc.getint(MAINSECTION, 'bufsize')
    self.interval = rc.getint(MAINSECTION, 'interval')
    self.skip = rc.getint(MAINSECTION, 'skip')
    self.fftw = rc.getint(MAINSECTION, 'fftw')
    self.overlap = rc.getfloat(MAINSECTION, 'overlap')
    self.nonce = rc.get(MAINSECTION, 'nonce')
    self.floor = rc.getfloat(MAINSECTION, 'floor')
    self.sql = rc.getfloat(MAINSECTION, 'sql')
    self.transition = rc.getfloat(MAINSECTION, 'transition')
    self.minw = rc.getint(MAINSECTION, 'minw')*1000
    self.maxw = rc.getint(MAINSECTION, 'maxw')*1000
    self.spacing = rc.getint(MAINSECTION, 'spacing')*1000
    self.gain = rc.get(MAINSECTION, 'gain')

    self.samplerate = samplerate

    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]

    self.scanframes = []
    self.cronframes = []

    step = float(samplerate) * (1-self.overlap)

    # Read scanframe and channel config files
    for f in files:
      if f == "main.conf":
        continue

      print("file %s"%f)

      rc = configparser.ConfigParser()
      rc.read(os.path.join(path, f))

      try:
        floor = rc.getfloat(MAINSECTION, 'floor')
      except:
        floor = self.floor

      try:
        sql = rc.getfloat(MAINSECTION, 'sql')
      except:
        sql = self.sql

      if "freqstart" in rc.options(MAINSECTION): # range randscan
        freqstart = rc.getint(MAINSECTION, "freqstart")*1000 + step/2
        freqstop = rc.getint(MAINSECTION, "freqstop")*1000 - step/2
        numf = int(math.ceil(float(freqstop - freqstart)/step))
        delta = float(freqstop - freqstart) / numf
        cf = freqstart
        while cf < math.ceil(freqstop):
          frm = scanframe()
          frm.freq = cf
          frm.floor = floor
          frm.sql = sql
          frm.gain = self.gain

          self.scanframes.append(frm)
          print("insert %f"%cf)
          cf += math.floor(delta)
      elif "cron" in rc.options(MAINSECTION): # scheduled recording
        channels = self.channel_list_from_config(rc)

        frm = cronframe()
        frm.freq = rc.getint(MAINSECTION, "freq")*1000
        frm.floor = "floor"
        frm.sql = sql
        frm.gain = self.gain
        frm.cron = rc.get(MAINSECTION, "cron")
        frm.cronlen = rc.getint(MAINSECTION, "cronlen")
        frm.channels = channels

        self.cronframes.append(frm)

      try:
        randscan = rc.getboolean(MAINSECTION, "randscan")
      except:
        randscan = True
      

      if ((not ("freqstart" in rc.options(MAINSECTION))) and randscan):
        frm = scanframe()
        frm.freq = rc.getint(MAINSECTION, "freq")*1000
        frm.floor = floor
        frm.sql = sql
        frm.gain = self.gain

        channels = self.channel_list_from_config(rc)
        frm.channels = channels

        self.scanframes.append(frm)

  def channel_list_from_config(self, rc):
    channels = []
    for ssect in rc.sections():
      if ssect == MAINSECTION:
        continue

      ch = channel()
      ch.freq = rc.getint(ssect, "freq")*1000
      ch.bw = rc.getint(ssect, "bw")*1000
      taps = firdes.low_pass(1, self.samplerate, ch.bw, ch.bw*self.transition, firdes.WIN_HAMMING)
      ch.taps = struct.pack("=%if"%len(taps), *taps)

      try:
        ch.cont = rc.getint(ssect, "continue")
      except:
        ch.cont = 0

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


