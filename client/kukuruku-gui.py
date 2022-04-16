#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import struct
import queue
import time
from datetime import datetime
import cairo
import math
import subprocess

from colormap import colormap

from threading  import Thread, Lock, Condition

import libutil

import libclient

from ClientStructures import XlaterHelper, Mode
from ConfReader import ConfReader, read_modes
from getfir import getfir

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk


Gdk.threads_init()

# get configuration
conf = ConfReader(os.getenv('HOME') + '/.kukuruku/gui')

# initialize the graphic stuff
vbox = Gtk.VBox(False, 0)
screen = None
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

wait_for_info = Condition()

window = Gtk.Window()
toolbar = Gtk.Toolbar()
toolbar.set_style(Gtk.ToolbarStyle.ICONS)
tb_record = Gtk.ToolButton(stock_id=Gtk.STOCK_MEDIA_RECORD)
tb_record.set_tooltip_text("Record the entire baseband")
tb_dump = Gtk.ToolButton(stock_id=Gtk.STOCK_SAVE)
tb_dump.set_tooltip_text("Dump the entire baseband history + start recording")
tb_freq_label = Gtk.Label(label="Frequency")
tb_freq = Gtk.Entry()
tb_freq_plus = Gtk.ToolButton(stock_id=Gtk.STOCK_GO_FORWARD)
tb_freq_minus = Gtk.ToolButton(stock_id=Gtk.STOCK_GO_BACK)
tb_ppm_label = Gtk.Label(label="PPM")
tb_ppm = Gtk.Entry()
tb_gain_label = Gtk.Label(label="Gain")
tb_gain = Gtk.Entry()
tb_sql_label = Gtk.Label(label="SQL")
tb_sql = Gtk.Entry()
tb_cursor_label = Gtk.Label(label=" --- ")

samplerate = 1
# save the last coordinate of click on drawing area here
wf_click_x = 0
wf_click_y = 0
frequency = 0

XlaterHelpers = {}

def is_enter(event):
  """
  True if event is Gtk.Event of pressing Enter
  """
  return event.keyval == Gdk.KEY_Return

def float2color(f):
  """
  Get color index from power readings
  """
  idx = conf.spectrumscale*(f + conf.spectrumoffset)
  return max(0, min(libutil.safe_cast(idx, int, 0), len(colormap)-1))

def pixel2freq(pixpos):
  """
  X position in waterfall to corresponding frequency
  """
  return -0.5*samplerate + ((pixpos-conf.borderleft)/(conf.fftw)) * samplerate

def freq2pixel(freq):
  """
  Frequency to X position in waterfall
  """
  return int((freq + (0.5*samplerate)) * (float(conf.fftw)/samplerate))

def pixel2frame(pixpos):
  """
  Y position in waterfall to corresponding frame number
  """
  if not pixpos in fftframes:
    return min(fftframes.values())
  return fftframes[pixpos]

def pixel2xlater(pixpos):
  """
  X position in waterfall to corresponding xlater wid (or None if there is none)
  """
  f = pixel2freq(pixpos)
  x = cl.get_xlaters()

  for key in x:
    bw = samplerate/x[key].decimation
    offset = -x[key].rotate*samplerate/(2*math.pi)

    if abs(offset - f) < bw/2:
      return key

  return None


def info_cb(msg):
  """ Extract information from INFO message """
  global samplerate, frequency, ppm, gain, packetlen, bufsize, maxtaps

  wait_for_info.acquire()

  samplerate = msg.samplerate
  frequency = msg.frequency
  ppm = msg.ppm
  _fftw = msg.fftw
  gain = []
  gain.append(msg.autogain)
  gain.append(msg.global_gain)
  gain.append(msg.if_gain)
  gain.append(msg.bb_gain)
  packetlen = msg.packetlen
  bufsize = msg.bufsize
  maxtaps = msg.maxtaps

  tb_freq.set_text(str(frequency))
  tb_ppm.set_text(str(ppm))

  tb_gain.set_text("%i,%i,%i,%i"%(gain[0], gain[1], gain[2], gain[3]))

  conf.fftw = _fftw

  # signal that we have received server info and the GUI can now run
  wait_for_info.notify()
  wait_for_info.release()

# current line in the waterfall
wfofs = 0
# last spectrum measurement
lastfft = None
# dictionary y position -> frameno
fftframes = {}
# dictionary y position -> timestamp
ffttimes = {}
# dictionary y position -> list of power data [dB]
fftpowers = {}
# timestamp of last message in the left border
fft_lastshowntime = 0

def fft_cb(d, frameno, timestamp):
  """ Handle spectrum measurement. Put color pixels to waterfall. """
  global wfofs, lastfft, fft_lastshowntime, conf, screen, screenw

  data = None
  while(len(d) >= conf.fftw):
    data = d[:conf.fftw]
    for i in range(0, len(data)):
      idx = float2color(data[i])
      screen.set_source_rgb(*colormap[idx])
      screen.rectangle(conf.borderleft+i, wfofs, 1, 1)
      screen.fill()

    for x in cl.xlaters.values():
      bw = samplerate/x.decimation
      offset = -x.rotate*samplerate/(2*math.pi)
      p1 = freq2pixel(offset - bw/2)
      p2 = freq2pixel(offset + bw/2)

      color = [BLACK, WHITE][wfofs%2]

      screen.set_source_rgb(*color)
      screen.rectangle(conf.borderleft+p1, wfofs, 1, 1)
      screen.fill()
      screen.rectangle(conf.borderleft+p2, wfofs, 1, 1)
      screen.fill()

    fftframes[wfofs] = frameno
    ffttimes[wfofs] = timestamp
    fftpowers[wfofs] = data

    if fft_lastshowntime + 4.5 < timestamp and wfofs > conf.fontsize and timestamp % 5 == 0:
      wow = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S %y%m%d")
      ypos = max(0, wfofs)
      screen.set_source_rgb(*WHITE)
      screen.move_to(0, ypos)
      screen.show_text(wow)
      fft_lastshowntime = timestamp

    wfofs = (wfofs+1)%da_height
    d = d[conf.fftw:]

    screen.set_line_width(1)
    screen.set_source_rgb(*BLACK)
    screen.move_to(0.5, wfofs + 0.5)
    screen.line_to(conf.borderleft + conf.fftw + 0.5, wfofs + 0.5)
    screen.stroke()
    screen.set_source_rgb(*WHITE)
    screen.move_to(0.5, (wfofs+1)%da_height + 0.5)
    screen.line_to(conf.borderleft + conf.fftw + 0.5, (wfofs+1)%da_height + 0.5)
    screen.stroke()
  screenw.queue_draw()

  if not lastfft:
    lastfft = data
    on_fftscale(None) # use the first measurement to at least coarsely adjust the color scheme
  lastfft = data

def sql_cb(rotation, decimation):
  """ Evaluate squelch for a channel, see documentation to libclient """
  if not lastfft:
    return True
  centerbin = int(-rotation*conf.fftw/(2*math.pi) + conf.fftw/2)
  rangebins = int(conf.fftw/decimation/2)

  cutoff = sorted(lastfft)[int(conf.sqltrim * conf.fftw)]

  ave = 0.0
  items = 0.0
  for i in range(centerbin-rangebins, centerbin+rangebins):
    if i < 0 or i > conf.fftw-1:
      continue
    ave += lastfft[i]
    items += 1
  ave /= items

  relevant = lastfft[centerbin-rangebins:centerbin+rangebins]
  if not relevant:
    print("squelch: extracted empty measurement")
    return True

  ave = max(lastfft[centerbin-rangebins:centerbin+rangebins])

  print("cutoff %f, range %i +/- %i, ave %f"%(cutoff, centerbin, rangebins, ave))

  if ave - conf.sqldelta > cutoff:
    print("true")
    return True
  print("false")
  return False


def histo_cb(d):
  """ Display histogram data """
  global screen, screenw
  xlim = max(d)
  for i in range(0, conf.histobars):
    bar = d[i]*conf.histow/xlim
    y = conf.histobars-i
    screen.set_line_width(1)
    screen.set_source_rgb(*WHITE)
    screen.move_to(conf.borderleft + conf.fftw + conf.histooffs + 0.5, y + 0.5)
    screen.line_to(conf.borderleft + conf.fftw + conf.histooffs + bar + 0.5, y + 0.5)
    screen.stroke()
    screen.set_source_rgb(*BLACK)
    screen.move_to(conf.borderleft + conf.fftw + conf.histooffs + bar + 1 + 0.5, y + 0.5)
    screen.line_to(conf.borderleft + conf.fftw + conf.histooffs + conf.histow + 0.5, y + 0.5)
    screen.stroke()
  screenw.queue_draw()

def xlater_cb():
  """ Write changes in libclient.xlaters to the GUI listview """
  # delete old xlaters

  while True:
    deleted = False
    xls = cl.get_xlaters()
    for i in range(0, len(model)):
      wid = model[i][0]
      if not wid in xls and wid != -1:
        del(model[i])
        deleted = True
        break
    if not deleted:
      break

  # add new, update existing
  for wid in xls:
    row = find_wid(wid)
    if row is None:
      lowpass = samplerate/xls[wid].decimation/2
      transition = 0.1*lowpass
      filtertype = "hamming"
      rid = xls[wid].rid
      if rid in XlaterHelpers:
        lowpass = XlaterHelpers[rid].lowpass
        filtertype = XlaterHelpers[rid].filtertype
        transition = XlaterHelpers[rid].transition

      make_panel(wid, -xls[wid].rotate*samplerate/(2*math.pi),
                 lowpass, filtertype, transition, False, False)
    else:
      model[row][1] = -xls[wid].rotate*samplerate/(2*math.pi)
      model[row][7] = frequency + model[row][1]

def find_wid(wid):
  """ Return row ID in model that has the xlated WID """
  for i in range(0, len(model)):
    if model[i][0] == wid:
      return i
  return None

def make_panel(wid, offset, bw, filtertype, transition, sql, afc):
  """ Create new xlater in model """
  model.append(None)
  model[-1] = [int(wid), libutil.safe_cast(offset, int, 0), filtertype, libutil.safe_cast(transition, int, 0),
               libutil.safe_cast(bw, int, 0), afc, sql, libutil.safe_cast(frequency + offset, int, 0)]

def on_demod(widget, event):
  """ The item in context menu was selected. Create new xlater. """
  global myxln, wf_click_x, wf_click_y, samplerate, maxtaps

  for mode in modes: # find mode
    if widget == modes[mode].button:

      cl.acquire_xlaters()
      wid = pixel2xlater(wf_click_x)
      if wid is not None: # user clicked on a running xlater
        cl.enable_xlater(wid, conf.preferformat)

        decimation = cl.get_xlaters()[wid].decimation
        rate = int(round(float(samplerate) / decimation))
        resample = (float(samplerate)/decimation) / modes[mode].rate

        if samplerate % rate != 0 and not modes[mode].resample:
          showerror("SDR samplerate %i must be an integer multiple of module samplerate %i!"%(samplerate, modes[mode].rate))
          cl.release_xlaters()
          return True

        program = modes[mode].program.replace("_MODEPATH_", conf.modepath)
        if samplerate % rate != 0:
          print("decim %i, resample ratio = %f"%(decimation, resample))
          program += " -r %f"%resample

        cl.subscribe_xlater(wid, program)

      else: # no xlater running here, we need to create one
        offset = pixel2freq(wf_click_x)
        startframe = -1

        if event.get_state() & Gdk.ModifierType.CONTROL_MASK:
          startframe = pixel2frame(wf_click_y)
        print("freq %i x %i y %i hist %i"%(offset, wf_click_x, wf_click_y, startframe))

        decimation = int(round(float(samplerate) / modes[mode].rate))
        resample = (float(samplerate)/decimation) / modes[mode].rate

        if samplerate % modes[mode].rate != 0 and not modes[mode].resample:
          showerror("SDR samplerate %i must be an integer multiple of module samplerate %i!"%(samplerate, modes[mode].rate))
          cl.release_xlaters()
          return True

        rotate = -(offset/samplerate)*2*math.pi

        program = modes[mode].program.replace("_MODEPATH_", conf.modepath)
        if samplerate % modes[mode].rate != 0:
          program += " -r %f"%resample
          print("decim %i, resample ratio = %f"%(decimation, resample))

        rid = cl.create_xlater(rotate,
                               decimation,
                               getfir(samplerate, modes[mode].filtertype, modes[mode].bw, modes[mode].transition, maxtaps),
                               program,
                               startframe)

        h = XlaterHelper()
        h.lowpass = modes[mode].bw
        h.transition = modes[mode].transition
        h.filtertype = modes[mode].filtertype

        XlaterHelpers[rid] = h

      cl.release_xlaters()
      return True

def on_fftscale(widget):
  """
  Set waterfall dynamic range and offset according to the last measurement
  """
  global conf, lastfft

  if not lastfft:
    print("no data to calibrate")
    return

  delta = max(lastfft) - min(lastfft)

  conf.spectrumoffset = -min(lastfft) + 0.125*delta
  conf.spectrumscale = 768/delta

  return True

def da_press(widget, event):
  """ Handle button press on display area """
  global wf_click_x,wf_click_y

  # ignore presses outside drawing area
  if event.get_coords()[0] < conf.borderleft or event.get_coords()[0] > conf.borderleft+conf.fftw:
    return

  # right click
  if event.type == Gdk.EventType.BUTTON_RELEASE and event.button == 3:
    menu.popup(None, None, None, None, event.button, event.time)

  # release on move
  if event.type == Gdk.EventType.BUTTON_RELEASE and event.button == 1:
    cl.acquire_xlaters()
    wid = pixel2xlater(wf_click_x)
    if wid is not None:
      row = find_wid(wid)
      if row is not None:
        model[row][1] = pixel2freq(event.get_coords()[0])
        model[row][7] = frequency + model[row][1]
        commit_xlater(row)
    cl.release_xlaters()

  wf_click_x = event.get_coords()[0]
  wf_click_y = event.get_coords()[1]

def da_scroll(widget, event):
  """ Handle scroll event on display area """
  cl.acquire_xlaters()
  wid = pixel2xlater(event.get_coords()[0])
  if wid is not None:
    row = find_wid(wid)
    if row is not None:

      if event.direction == Gdk.ScrollDirection.UP:
        newbw = 1.2*model[row][4]
      elif event.direction == Gdk.ScrollDirection.DOWN:
        newbw = 0.8*model[row][4]

      model[row][4] = int(newbw)
      commit_xlater(row)
  cl.release_xlaters()

def da_motion(widget, event):
  """ Handle cursor motion event on display area """
  freq = pixel2freq(event.get_coords()[0]) + frequency;
  freq /= 1000

  y = event.get_coords()[1]
  timestamp = 0
  dbstr = "?"
  if y in ffttimes.keys():
    timestamp = ffttimes[y]
  if y in fftpowers.keys():
    pwr = fftpowers[y][min(conf.fftw-1, max(0, int(event.get_coords()[0]-conf.borderleft)))]
    dbstr = "%.1f"%pwr

  datestr = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
  tb_cursor_label.set_text("%i kHz, %s, %s dB"%(freq, datestr, dbstr))

def on_freq_change(widget, event):
  """ Handle edit in the Frequency textbox """
  global frequency

  if not is_enter(event):
    return False

  newf = libutil.safe_cast(libutil.engnum(tb_freq.get_text()), int)
  if newf:
    cl.set_frequency(newf)
    frequency = newf
  return True

def on_freq_plus(widget):
  """ Frequency '>' button """
  global frequency
  frequency = frequency + samplerate*0.8
  cl.set_frequency(frequency)
  tb_freq.set_text(str(frequency))

def on_freq_minus(widget):
  """ Frequency '<' button """
  global frequency
  frequency = frequency - samplerate*0.8
  cl.set_frequency(frequency)
  tb_freq.set_text(str(frequency))

def on_ppm_change(widget, event):
  """ Handle edit in the PPM textbox """
  global ppm

  if not is_enter(event):
    return False

  ppm = libutil.safe_cast(tb_ppm.get_text(), int, ppm)
  tb_ppm.set_text(str(ppm))

  cl.set_ppm(ppm)

def on_gain_change(widget, event):
  """  Handle edit in the Gain textbox """
  if not is_enter(event):
    return False

  #if tb_gain.get_text() in ["a", "A", "auto"]:
  #  cl.set_gain(1, [0])
  #else:
  pieces = tb_gain.get_text().split(",")
  l = []
  for p in pieces:
    l.append(libutil.safe_cast(p, int, 0))
  cl.set_gain(l)

def on_sql_change(widget, event):
  """ Handle edit in the SQL textbox """
  global conf

  if not is_enter(event):
    return False

  conf.sqldelta = libutil.safe_cast(tb_sql.get_text(), float, conf.sqldelta)
  tb_sql.set_text(str(conf.sqldelta))

def stop_record():
  cl.record(-1, -10)                                                          
  tb_record.set_stock_id(Gtk.STOCK_MEDIA_RECORD)                              
  tb_dump.set_stock_id(Gtk.STOCK_SAVE)  

def on_record(widget):
  """ Record button pressed """
  if tb_record.get_stock_id() == Gtk.STOCK_MEDIA_RECORD:
    cl.record(-1, 2**31-1)
    tb_record.set_stock_id(Gtk.STOCK_MEDIA_STOP)
    tb_dump.set_stock_id(Gtk.STOCK_MEDIA_STOP)
  else:
    stop_record()

def on_dump(widget):
  """ Dump button pressed """
  if tb_dump.get_stock_id() == Gtk.STOCK_SAVE:
    cur = max(fftframes.values())
    cl.record(cur-bufsize, 2**31-1)
    tb_dump.set_stock_id(Gtk.STOCK_MEDIA_STOP)
    tb_record.set_stock_id(Gtk.STOCK_MEDIA_STOP)
  else:
    stop_record()

def da_configure(widget, data=None):
  """
  Steal SDL window from GTK, draw to it
  """
  global screen, screenw, surface

  surface = widget.get_window().create_similar_surface(cairo.CONTENT_COLOR, da_width, da_height)
  screenw = widget
  screen = cairo.Context(surface)

  Gdk.flush()

  screen.set_font_size(conf.fontsize)
  screen.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
  screen.set_source_rgb(*WHITE)
  screen.move_to(100, 200)
  screen.show_text("Kukuruku client (c) 2014-2016 NSA Litomerice")

  cl.set_fft_callback(fft_cb)
  cl.set_sql_callback(sql_cb)
  cl.set_histo_callback(histo_cb)
  cl.set_xlater_callback(xlater_cb)
  cl.list_xlaters()

def da_draw(widget, cairo):
  """ Refresh display area on expose """
  global surface
  cairo.set_source_surface(surface, 0, 0)
  cairo.paint()
  return True


wait_for_info.acquire()
cl = libclient.client()

if len(sys.argv) >= 2:
  (conf.HOST, conf.PORT) = sys.argv[1].split(":")
  conf.PORT = int(conf.PORT)

cl.set_auto_enable_xlater(True, conf.preferformat)
cl.set_info_callback(info_cb)
cl.connect(conf.HOST, conf.PORT)
cl.set_afc_params(conf.afcdecim, conf.afcmult)
cl.enable_histo()
cl.enable_spectrum()

modes = read_modes(os.getenv('HOME') + '/.kukuruku/modes')

# Connect callbacks to buttons
tb_record.connect("clicked", on_record)

tb_dump.connect("clicked", on_dump)

tb_scale = Gtk.ToolButton(stock_id=Gtk.STOCK_SELECT_COLOR)
tb_scale.set_tooltip_text("Autorange the colors in waterfall")
tb_scale.connect("clicked", on_fftscale)

tb_freq.connect("key-press-event", on_freq_change)
tb_freq.set_size_request(110, -1)

tb_freq_plus.connect("clicked", on_freq_plus)
tb_freq_minus.connect("clicked", on_freq_minus)

tb_ppm.connect("key-press-event", on_ppm_change)
tb_ppm.set_size_request(35, -1)

tb_gain.connect("key-press-event", on_gain_change)
tb_gain.set_size_request(100, -1)

tb_sql.set_text(str(conf.sqldelta))
tb_sql.connect("key-press-event", on_sql_change)
tb_sql.set_size_request(35, -1)

# put buttons to toolbar
for item in [tb_record, tb_scale, tb_dump, tb_freq_label, tb_freq_minus, tb_freq, tb_freq_plus,
             tb_ppm_label, tb_ppm, tb_gain_label, tb_gain, tb_sql_label, tb_sql, tb_cursor_label]:
  if isinstance(item, Gtk.Label):
    toolbar.insert(Gtk.SeparatorToolItem(), -1)
  if isinstance(item, Gtk.ToolButton):
    toolbar.insert(item, -1)
  else:
    wrapper= Gtk.ToolItem()
    wrapper.add(item)
    toolbar.insert(wrapper, -1)

# add toolbar to the vertical box layout
vbox.pack_start(toolbar, False, False, 0)

def afc_toggle_cb(cell, path):
  """ AFC checkbox """
  model[path][5] = not model[path][5]
  cl.set_afc(model[path][0], model[path][5])

def sql_toggle_cb(cell, path):
  """ SQL checkbox """
  model[path][6] = not model[path][6]
  cl.set_squelch(model[path][0], model[path][6])

def kill_toggle_cb(cell, path):
  """ Kill checkbox """
  wid = model[path][0]
  cl.destroy_xlater(wid)

def xlater_edit(cell, row, new_value, field):
  """ Row in listview changed """
  cl.acquire_xlaters()
  newcast = libutil.safe_cast(libutil.engnum(new_value), type(model[row][field]))

  if not newcast:
    showerror("Value was not understood")
    return

  # handle frequency/offset consistency
  if field == 7:
    model[row][1] = newcast - frequency
  elif field == 1:
    model[row][7] = frequency + newcast

  model[row][field] = newcast
  commit_xlater(row)
  cl.release_xlaters()

def commit_xlater(row):
  """ Update xlater on change """
  rotate = -(float(model[row][1])/samplerate)*2*math.pi

  cl.modify_xlater(model[row][0], rotate,
  getfir(samplerate, model[row][2], model[row][4], model[row][3], maxtaps))

def showerror(s):
  """
  Display alert message box
  """
  message = Gtk.MessageDialog(None, 0, Gtk.MESSAGE_ERROR, Gtk.BUTTONS_CLOSE, s)
  message.run()
  message.destroy()


# create and add scrollview with treeview with xlaters
model = Gtk.TreeStore(int,  # wid
                      int,  # offset
                      str,  # type
                      int,  # transition
                      int,  # lowpass
                      bool, # AFC
                      bool, # SQL
                      int)  # freq
treeView = Gtk.TreeView(model=model)

# ID column
renderer = Gtk.CellRendererText()
column = Gtk.TreeViewColumn('ID', renderer, text=0)
treeView.append_column(column)

# Offset column
renderer = Gtk.CellRendererText()
renderer.set_property('editable', True)
renderer.connect('edited', xlater_edit, 1)
column = Gtk.TreeViewColumn('Offset', renderer, text=1)
treeView.append_column(column)

# FIR type column
renderer = Gtk.CellRendererText()
renderer.set_property('editable', True)
renderer.connect('edited', xlater_edit, 2)
column = Gtk.TreeViewColumn('FIR type', renderer, text=2)
treeView.append_column(column)

# Lowpass column
renderer = Gtk.CellRendererText()
renderer.set_property('editable', True)
renderer.connect('edited', xlater_edit, 4)
column = Gtk.TreeViewColumn('Lowpass', renderer, text=4)
treeView.append_column(column)

# AFC checkbox column
renderer = Gtk.CellRendererToggle()
column = Gtk.TreeViewColumn('AFC', renderer, active=5)
renderer.set_property('activatable', True)
renderer.connect('toggled', afc_toggle_cb)
treeView.append_column(column)

# SQL checkbox column
renderer = Gtk.CellRendererToggle()
column = Gtk.TreeViewColumn('SQL', renderer, active=6)
renderer.set_property('activatable', True)
renderer.connect('toggled', sql_toggle_cb)
treeView.append_column(column)

# Frequency column
renderer = Gtk.CellRendererText()
renderer.set_property('editable', True)
renderer.connect('edited', xlater_edit, 7)
column = Gtk.TreeViewColumn('Frequency', renderer, text=7)
treeView.append_column(column)

# Kill checkbox column
renderer = Gtk.CellRendererToggle()
column = Gtk.TreeViewColumn('Kill', renderer)
renderer.set_property('activatable', True)
renderer.connect('toggled', kill_toggle_cb)
treeView.append_column(column)

scrolled_window = Gtk.ScrolledWindow()
scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
scrolled_window.set_size_request(conf.borderleft, conf.areabottom)

scrolled_window.add(treeView)

vbox.pack_end(scrolled_window, False, True, 0)
window.add(vbox)

# populate the right-click menu
menu = Gtk.Menu()
for mode in sorted(modes, key = lambda m: modes[m].name):
  menu_item = Gtk.MenuItem(label=modes[mode].name)
  modes[mode].button = menu_item
  menu_item.connect("button_press_event", on_demod)
  menu.append(menu_item)
  menu_item.show()

# create the main drawing area
# wait until we know the FFT size the server uses!
if conf.fftw is not None:
  raise RuntimeError("fftw set before we wanted to wait for it???")
wait_for_info.wait()
wait_for_info.release()

da_width = conf.borderleft + conf.fftw + conf.histow + conf.histooffs
da_height = conf.drawingheight

# Put it into layout into table with horizontal scrolling.
layout = Gtk.Layout()
layout.set_size_request(1024, da_height)
layout.set_size(da_width, da_height)
table = Gtk.Table(n_rows=2, n_columns=1, homogeneous=False)
table.attach(layout, 0, 1, 0, 1, Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, 0, 0)

hScrollbar = Gtk.HScrollbar(adjustment=None)
table.attach(hScrollbar, 0, 1, 1, 2, Gtk.AttachOptions.FILL|Gtk.AttachOptions.SHRINK, Gtk.AttachOptions.FILL|Gtk.AttachOptions.SHRINK, 0, 0)

hAdjust = layout.get_hadjustment()
hScrollbar.set_adjustment(hAdjust)

drawing_area = Gtk.DrawingArea()
drawing_area.set_size_request(da_width, da_height)
drawing_area.connect("configure-event", da_configure)
drawing_area.connect("draw", da_draw)
drawing_area.show()

drawing_area.connect("button_press_event", da_press)
drawing_area.connect("button_release_event", da_press)
drawing_area.connect("scroll-event", da_scroll)
drawing_area.connect("motion-notify-event", da_motion)
# Catch mouse events incl. scroll and move
drawing_area.add_events(Gdk.EventMask.BUTTON_RELEASE_MASK |
  Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK)

layout.put(drawing_area, 0, 0)
vbox.pack_start(table, True, True, 0)

def exit(widget):
  cl.disconnect()
  Gtk.main_quit()
  sys.exit(0)

window.connect("destroy", exit)
window.maximize()
window.show_all()

window.set_title("%s:%i - Kukuruku client"%(conf.HOST, conf.PORT))

Gtk.main()

