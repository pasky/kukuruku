import libutil

def XlaterHelper():
  """ Structure for holding xlater data that are not sent and received to the server. """
  XlaterHelperT = libutil.Struct("XlaterHelper", "lowpass filtertype transition")
  return XlaterHelperT(None, None)

def Mode():
  """ Parsed mode from "modes" config file. """
  ModeT = libutil.Struct("mode", "name rate bw transition filtertype program button resample")
  return ModeT(None, None, None, None, None, None, None, None, False)

