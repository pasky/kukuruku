import configparser
from ClientStructures import Mode
from libutil import cfg_safe

class ConfReader():
  """ Read Kukuruku gui config from file in path """

  def __init__(self, path):
    rc = configparser.ConfigParser()
    rc.read(path)
    section = "Main"
    cfpath = path
    self.HOST = cfg_safe(rc.get, section, 'host', "localhost", cfpath)
    self.PORT = cfg_safe(rc.getint, section, 'port', 4444, cfpath)
    self.mousechangedelay = cfg_safe(rc.getint, section, 'mousechangedelay', 1, cfpath)
    self.histooffs = cfg_safe(rc.getint, section, 'histooffs', 1, cfpath)
    self.histow = cfg_safe(rc.getint, section, 'histow', 50, cfpath)
    self.histobars = cfg_safe(rc.getint, section, 'histobars', 256, cfpath)
    self.drawingheight = cfg_safe(rc.getint, section, 'drawingheight', 540, cfpath)
    self.borderleft = cfg_safe(rc.getint, section, 'borderleft', 80, cfpath)
    self.areabottom = cfg_safe(rc.getint, section, 'areabottom', 120, cfpath)
    self.fontsize = cfg_safe(rc.getint, section, 'fontsize', 12, cfpath)
    self.antialias = cfg_safe(rc.getboolean, section, 'antialias', False, cfpath)
    self.spectrumscale = cfg_safe(rc.getint, section, 'spectrumscale', 50, cfpath)
    self.spectrumoffset = cfg_safe(rc.getint, section, 'spectrumoffset', 6, cfpath)
    self.sqltrim = cfg_safe(rc.getfloat, section, 'sqltrim', 0.3, cfpath)
    self.sqldelta = cfg_safe(rc.getfloat, section, 'sqldelta', 10, cfpath)
    self.afcdecim = cfg_safe(rc.getfloat, section, 'afcdecim', 5, cfpath)
    self.afcmult = cfg_safe(rc.getfloat, section, 'afcmult', 0.1, cfpath)
    self.modepath = cfg_safe(rc.get, section, 'modepath', "./modes", cfpath)
    self.preferformat = cfg_safe(rc.get, section, 'preferformat', "F32", cfpath)
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
