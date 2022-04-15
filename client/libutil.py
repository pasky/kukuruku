def Struct(name, fields):
  """ class generator like namedtuple, but not immutable
   https://stackoverflow.com/questions/3648442/python-how-to-define-a-structure-like-in-c/3648450#3648450
  """
  fields = fields.split()
  def init(self, *values):
    for field, value in zip(fields, values):
      self.__dict__[field] = value
  cls = type(name, (object,), {'__init__': init})
  return cls

def safe_cast(val, to_type, default=None):
  """ Cast val to to_type, return default if it fails. """
  try:
    return to_type(val)
  except:
    return default

def engnum(s):
  """ Convert string s containing number with postfix k, K, M, m, G, g to float.
      We regard "m" as Mega because we don't want to bother the user with pressing shift
      and there is really no use for milli here.
  """

  if isinstance(s, (int, long, float)):
    return s

  i = safe_cast(s, int)
  if s[-1] == "k" or s[-1] == "K":
    s = s[:-1]
    i = safe_cast(s, float)
    if i is not None:
      i *= 1000

  if s[-1] == "m" or s[-1] == "M":
    s = s[:-1]
    i = safe_cast(s, float)
    if i is not None:
      i *= 1000*1000

  if s[-1] == "g" or s[-1] == "G":
    s = s[:-1]
    i = safe_cast(s, float)
    if i is not None:
      i *= 1000*1000

  return i

def cfg_safe(func, section, key, default, f = None):
  """ Try reading key from section with configparser func.
  If it is not there, return default, and if f is set, print warning with this
  as a file name where it is missing.
  The configparser has some default dictionary, but it somehow didn't work for
  anything other than strings.
  """
  try:
    x = func(section, key)
  except:
    x = default
    if f is not None:
      print("Can't get configuration key %s from section %s in %s. Using default %s."%(key, section, f, default))
  return x


