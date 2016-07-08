import configparser
from ClientStructures import Mode

class ConfReader():
  """ Read config from file in path """

  def __init__(self, path):
    rc = configparser.ConfigParser()
    rc.read(path)
    section = "Main"
    self.HOST = rc.get(section, 'host')
    self.PORT = rc.getint(section, 'port')
    self.mousechangedelay = rc.getint(section, 'mousechangedelay')
    self.histooffs = rc.getint(section, 'histooffs')
    self.histow = rc.getint(section, 'histow')
    self.histobars = rc.getint(section, 'histobars')
    self.drawingheight = rc.getint(section, 'drawingheight')
    self.borderleft = rc.getint(section, 'borderleft')
    self.areabottom = rc.getint(section, 'areabottom')
    self.fontsize = rc.getint(section, 'fontsize')
    self.antialias = rc.getboolean(section, 'antialias')
    self.spectrumscale = rc.getint(section, 'spectrumscale')
    self.spectrumoffset = rc.getint(section, 'spectrumoffset')
    self.sqltrim = rc.getfloat(section, 'sqltrim')
    self.sqldelta = rc.getfloat(section, 'sqldelta')
    self.afcdecim = rc.getfloat(section, 'afcdecim')
    self.afcmult = rc.getfloat(section, 'afcmult')
    self.modepath = rc.get(section, 'modepath')
    self.preferformat = rc.get(section, 'preferformat')
    self.fftw = None

def read_modes(path):
  """ Return dictionary of modes from file path """

  modes = {}

  modes_cfg = configparser.ConfigParser()
  modes_cfg.read(path)

  for section in modes_cfg.sections():
    modes[section] = Mode()
    modes[section].name = modes_cfg.get(section, "name")
    modes[section].rate = modes_cfg.getint(section, "rate")
    modes[section].bw = modes_cfg.getint(section, "bw")
    modes[section].filtertype = modes_cfg.get(section, "filtertype")
    modes[section].transition = modes_cfg.getint(section, "transition")
    modes[section].program = modes_cfg.get(section, "program")
    if modes_cfg.get(section, "resample"):
      modes[section].resample = True

  return modes
