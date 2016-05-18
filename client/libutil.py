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
  """ Convert string s containing number with postfix "k" or "M" to float """
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

  return i

