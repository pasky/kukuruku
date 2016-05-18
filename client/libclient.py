#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import struct
import Queue
import socket
import threading
import time
import math
import subprocess
import numpy as np
import libutil

# some protocol constants
class proto():
  DUMPBUFFER = 1
  RECORD_START = 2
  RECORD_STOP = 19
  CREATE_XLATER = 3
  LIST_XLATERS = 4
  DESTROY_XLATER = 5
  ENABLE_XLATER = 6
  DISABLE_XLATER = 7
  SET_GAIN = 8
  RETUNE = 9
  SET_PPM = 10
  SET_HISTO_FFT = 11
  SET_RATE = 12
  ENABLE_SPECTRUM = 13
  DISABLE_SPECTRUM = 14
  ENABLE_HISTO = 15
  DISABLE_HISTO = 16
  GET_INFO = 17
  MODIFY_XLATER = 18

  PAYLOAD = 256
  DUMPED = 257
  RUNNING_XLATER = 258
  INFO = 259

  PAYLOAD_SPECTRUM = -1
  PAYLOAD_HISTO = -2

def mylog(s):
  print(s)

class client():
  """ Class representing single connection to one server.
  We may implement multiple-servers-at-once client sometimes in the future
  if there would be a use-case for that.
  """

  def __init__(self):
    # running xlaters
    self.xlaters = {}
    # xlaters that were sent to the server, but the server has not yet replied
    self.xlater_q = {}

    self.xlaters_lock = threading.Lock()

    # TCP threads for reading and writing the socket + queue for asynchronous message sending
    self.tcp_r_t = None
    self.tcp_s_t = None
    self.msgq = Queue.Queue()

    self.sock = None

    self.fft_callback = None
    self.histo_callback = None
    self.info_callback = None
    self.sql_callback = None
    self.xlater_callback = None
    self.auto_enable_xlater = False

    self.afcdecim = 5
    self.afcmult = 0.0000001

    self.xln = 0

  def set_fft_callback(self, cb):
    """ Set the function that is called with the following parameters:
     binary string with array of floats
     int framenumber (a counter incrementing each frame since the server was started)
     int timestamp (unix timestamp when the frame was captured)
    """
    self.fft_callback = cb

  def set_sql_callback(self, cb):
    """ Set the function that is called with the following parameters:
     float rotate -- phase offset of the center of the channel
     int decimation -- decimation of the channel

     and is expected to return bool, True = squelch open, False = squelch closed
    """
    self.sql_callback = cb

  def set_histo_callback(self, cb):
    """ Set the function that is called with the following parameters:
     binary string with array of uint16_t, representing histogram of samples
    """
    self.histo_callback = cb

  def set_info_callback(self, cb):
    """ Set the function that is called with the following parameters:
     samplerate, frequency, ppm, gain, packetlen, fftw, bufsize, maxtaps
      representing the configuration of the remote radio
    """
    self.info_callback = cb

  def set_xlater_callback(self, cb):
    """ Set the function that is called without parameters every time 
     the xlaters{} dictionary has changed. The user is expected to e.g.
     update GUI elements with the xlaters.
    """
    self.xlater_callback = cb

  def set_auto_enable_xlater(self, val):
    """ Set whether to automatically invoke enable_xlater with create_xlater.
     val -- bool
    """
    self.auto_enable_xlater = val

  def set_afc_params(self, decim, mult):
    """ Set parameters of automatic frequency correction
     decim -- trigger AFC every N frames
     mult -- mulriply the obtained power difference with this value and add it to the rotator
       expected are very small numbers between 0.1 and 10 μ.
    """
    self.afcdecim = decim
    self.afcmult = mult

  def get_xlaters(self):
    """ Return dictionary of XlaterT (see docstring for Xlater) """
    return self.xlaters

  def acquire_xlaters(self):
    """ Lock the dictionary of xlaters. This is needed every time you manipulate
     with it if your application is running in multiple threads.
    """
    self.xlaters_lock.acquire()

  def release_xlaters(self):
    """ Unlock the dictionary of xlaters. See acquire_xlaters. """
    self.xlaters_lock.release()

  def connect(self, host, port):
    """ Connect to the server host:port. """

    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.connect((host, port))

    self.tcp_r_t = threading.Thread(target=self.tcp_receive_thr)
    self.tcp_r_t.daemon = True
    self.tcp_r_t.start()
    self.tcp_s_t = threading.Thread(target=self.tcp_send_thr)
    self.tcp_s_t.daemon = True
    self.tcp_s_t.start()

    msg = struct.pack("=i", proto.GET_INFO)
    self.q_msg(msg)
    msg = struct.pack("=i", proto.ENABLE_SPECTRUM)
    self.q_msg(msg)
    msg = struct.pack("=i", proto.ENABLE_HISTO)
    self.q_msg(msg)

  def disconnect(self):
    """ Close the client socket """
    self.sock.close()

  def record(self, startframe, duration):
    """ Trigger recording of the whole spectrum on the remote server.
     startframe -- first frame to record, -1 for current frame
     duration -- how many frames to record.
    """
    msg = struct.pack("=3i", proto.RECORD_START, startframe, duration)
    self.q_msg(msg)

  def create_xlater(self, rotate, decimation, taps, program, history):
    """ Create a new xlater on the server.
     rotate -- rotator in radians per sample
     taps -- list of FIR coefficients
     program -- shell command that will be executed and channel will be piped to it
     history -- first frame to process, -1 for current frame

     Return a local reference ID.
    """

    pending_xlater = self.Xlater()

    (pending_xlater.data, pending_xlater.thread) = self.spawn_mode(program)
    pending_xlater.decimation = decimation
    pending_xlater.rotate = rotate
    pending_xlater.rid = self.xln

    self.xlater_q[self.xln] = pending_xlater

    msgh = struct.pack("=iifii", proto.CREATE_XLATER, self.xln, rotate, decimation, history)
    msgt = struct.pack("=%if"%len(taps), *taps)

    self.q_msg(msgh+msgt)

    self.xln += 1

    return pending_xlater.rid

  def subscribe_xlater(self, xid, program):
    """ Spaen program and pipe the output of xlater ID xid to it. """
    (self.xlaters[xid].data, self.xlaters[xid].thread) = self.spawn_mode(program)

  def modify_xlater(self, xid, rotate, taps):
    """ Modify xlater XID, set rotator and new taps. If taps is None, only rotator is set. """

    self.xlaters[xid].rotate = rotate

    newtaps = 1
    if taps is None:
      newtaps = 0

    msgh = struct.pack("=iifi", proto.MODIFY_XLATER, xid, rotate, newtaps)
    msgt = b''
    if taps is not None:
      msgt = struct.pack("=%if"%len(taps), *taps)

    self.q_msg(msgh+msgt)

    if self.xlater_callback:
      self.xlater_callback()

  def destroy_xlater(self, xid):
    """ Remove an xlater from the remote server. """
    msg = struct.pack("=2i", proto.DESTROY_XLATER, xid)
    self.xlaters_lock.acquire()
    del(self.xlaters[xid])
    self.q_msg(msg)
    if self.xlater_callback:
      self.xlater_callback()
    self.xlaters_lock.release()

  def set_squelch(self, xid, val):
    """ Enable or disable squelch for xlater xid. """
    self.xlaters[xid].sql = val

  def set_afc(self, xid, val):
    """ Enable or disable AFC for xlater xid. """
    self.xlaters[xid].afc = val

  def feeder_thr(self, que, process):
    """ Thread that read from queue and wites to process stdin """
    while True:
      frame = que.get()
      try:
        process.stdin.write(frame)
      except IOError: # like when we get SIGPIPE on application quit
        break

  def spawn_mode(self, cmd):
    """ Spawn a process cmd, spawn feeder_thr for it, return reference to queue and thread. """
    process = subprocess.Popen([cmd], stdin=subprocess.PIPE, shell=True)
    que = Queue.Queue()
    t = threading.Thread(target=self.feeder_thr, args=(que, process), name="feeder_thr for %s"%cmd)
    t.daemon = True
    t.start()
    return (que, t)


  def q_msg(self, msg):
    """ Enqueue a message to be asynchronously sent to the server.
     The message is binary string and does not have the outer header ("length").
    """
    self.msgq.put(msg)


  def srv_running_xlater(self, packet):
    """ Respond to SRV_RUNNING_XLATER message. We add the xlater to xlaters{} """
    (rid, wid, rotate, decimation) = struct.unpack("=iifi", packet)

    xl = self.Xlater()

    self.xlaters_lock.acquire()

    if rid in self.xlater_q.keys():
      xl = self.xlater_q[rid]
      if self.auto_enable_xlater:
        self.enable_xlater(wid)
      del(self.xlater_q[rid])

    xl.rotate = rotate
    xl.decimation = decimation

    self.xlaters[wid] = xl

    if self.xlater_callback:
      self.xlater_callback()

    self.xlaters_lock.release()

    print("running xlater %i"%wid)

  def process_payload(self, d):
    """ Process a message from server. """

    (wid, time, frameno, stype) = struct.unpack("=4i", d[:16])

    if wid == proto.PAYLOAD_SPECTRUM: # spectrum, call fft_callback
      if self.fft_callback:
        self.fft_callback(d[16:], frameno, time)

    elif wid == proto.PAYLOAD_HISTO: # histogram, call histo_callback
      if self.histo_callback:
        self.histo_callback(d[16:])

    elif wid >= 0: # channel data
      self.xlaters_lock.acquire()
      if not wid in self.xlaters.keys(): # find xlater
        mylog("Xlater %i not running"%wid)
        self.xlaters_lock.release()
        return

      if not self.xlaters[wid].thread.isAlive():
        self.disable_xlater(wid)
        if self.xlater_callback:
          self.xlater_callback()
        self.xlaters_lock.release()
        return

      datacut = d[16:]

      if self.xlaters[wid].sql and self.sql_callback: # write according to squelch
        ret = self.sql_callback(self.xlaters[wid].rotate, self.xlaters[wid].decimation)
        if ret: # squelch open
          if self.xlaters[wid].sqlsave:
            self.xlaters[wid].data.put(self.xlaters[wid].sqlsave)
            self.xlaters[wid].sqlsave = None
          self.xlaters[wid].data.put(datacut)
        else: # squelch closed
          self.xlaters[wid].sqlsave = datacut

      else: # do not mess up with squelch -> always open
        self.xlaters[wid].data.put(datacut)

      if self.xlaters[wid].afc and frameno % self.afcdecim == 0: # evaluate AFC
        fftlen = 512
        iircoef = self.afcmult
        acc = np.zeros(fftlen)
        iters = 0
        window = np.hamming(fftlen)

        for i in range(0, len(datacut)-fftlen*8, fftlen*8): # compute short-time FFTs, sum result to acc
          dt = np.dtype("=c8")
          buf = np.frombuffer(datacut, count=fftlen, dtype=dt, offset = i)

          buf = buf*window

          fft = np.absolute(np.fft.fft(buf))
          acc += fft
          iters += 1

        left = np.sum(acc[:fftlen/2])  # sum power in the lower and upper part of the spectrum
        right = np.sum(acc[fftlen/2:])

        delta = (right-left) / iters * iircoef
        print("AFC change %f"%(delta))

        self.modify_xlater(wid, self.xlaters[wid].rotate + delta, None) # modify rotator with it

        if self.xlater_callback:
          self.xlater_callback()

      qs = self.xlaters[wid].data.qsize()
      if qs >= 50 and qs % 50 == 0:
        mylog("Worker %i (%s) queue has grown to %i"%(wid, self.xlaters[wid].thread, qs))
      self.xlaters_lock.release()

    else:
      mylog("Unknown payload worker %i"%wid)

  def process_info(self, d):
    """ Process SRV_INFO message, call info_callback """
    (samplerate, frequency, ppm, fftw) = struct.unpack("=iqii", d[:struct.calcsize("=iqii")])
    gain = struct.unpack("=4i", d[struct.calcsize("=iqii"):struct.calcsize("=iqii4i")])
    (packetlen, bufsize, maxtaps, stype) = struct.unpack("=iiii", d[struct.calcsize("=iqii4i"):])
    print("Remote says: samplerate %i, center frequency: %ik, ppm: %i, gain: %s, fft size: %i"%(samplerate, frequency/1000, ppm, gain, fftw))
    print("             samples per frame: %i, buffer length: %i frames, max FIR len: %i"%(packetlen, bufsize, maxtaps))
    if self.info_callback:
      self.info_callback(samplerate, frequency, ppm, gain, packetlen, fftw, bufsize, maxtaps)

  def enable_xlater(self, idx):
    msg = struct.pack("=3i", proto.ENABLE_XLATER, idx, 0)
    self.q_msg(msg)

  def disable_xlater(self, idx):
    msg = struct.pack("=2i", proto.DISABLE_XLATER, idx)
    self.q_msg(msg)

  def list_xlaters(self):
    msg = struct.pack("=i", proto.LIST_XLATERS)
    self.q_msg(msg)

  def set_frequency(self, f):
    print("tune %i"%f)
    msg = struct.pack("=iq", proto.RETUNE, f)
    self.q_msg(msg)

  def set_gain(self, gain):
    """ Set the gain parameters on the server.
     gr-osmosdr exports one boolean and three integer parameters. They are completely device-demendent.
      - The first one should enable or disable autogain. Some radios (Airspy, bladeRF) do not implement
         this at all.
      - The second is "RF gain". On most radios this is the main gain. Some radios (rtl-sdr) use this
         as an advice for autogain.
      - The third and fourth ones are baseband and interfrequency gain. Refer to documentation of your
         hardware for what exactly does this mean for it.

     The only parameter is a list of at least one element. The last element of the list is extended so
      the list has at least four elements.
    """
    msg = struct.pack("=i", proto.SET_GAIN)
    for i in range(0, 4):
      msg += struct.pack("=i", gain[min(len(gain)-1, i)])
    self.q_msg(msg)

  def set_ppm(self, ppm):
    msg = struct.pack("=2i", proto.SET_PPM, ppm)
    self.q_msg(msg)

  def Xlater(self):
    """ Structure to hold information about one running xlater
     float rotate -- rotator in radians per sample
     int decimation -- the ratio of sdr_samplerate/channel_samplerate
     bool sql -- apply squelch to this channel
     bool afc -- apply afc to this channel
     rid -- local reference ID
     thread -- feeder thread
     data -- queue of channel data that are written to program stdin
     sqlsave -- last frame in case of closed squelch, we use this to replay on frame on opening squelch
    """
    XlaterT = libutil.Struct("xlater", "rotate decimation sql afc rid thread data sqlsave")
    return XlaterT(None, None, False, False, None, None, None, None)

  def tcp_send_thr(cl):
    """ Read messages from msgq, write them to sock """
    while True:
      s = cl.msgq.get()
      l = len(s)
      h = struct.pack("=i", l)
      cl.sock.sendall(h)
      cl.sock.sendall(s)

  def getdata(self, req, remaining):
    """ Read "remaining" number of bytes from sock "req" """
    d = b''

    while remaining > 0:
      r = req.recv(min(remaining, 4096))
      if not r:
        return r
      remaining -= len(r)
      d += r

    return d

  def tcp_receive_thr(cl):
    """ Read messages from server, dispatch them to respective handlers """
    while True:
      d = cl.getdata(cl.sock, 4)
      l = struct.unpack("=i", d[:4])[0]
      d = cl.getdata(cl.sock, l)
      dtype = struct.unpack("=i", d[:4])[0]
      if dtype == proto.RUNNING_XLATER:
        cl.srv_running_xlater(d[4:])
      elif dtype == proto.PAYLOAD:
        cl.process_payload(d[4:])
      elif dtype == proto.INFO:
        cl.process_info(d[4:])
      else:
        mylog("unknown dtype %i", dtype)

