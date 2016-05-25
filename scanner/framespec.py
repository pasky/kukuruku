from libutil import Struct

def scanframe():
  ScanframeT = Struct("scanframe", "freq floor squelch channels gain")
  return ScanframeT(None, None, None, [])

def cronframe():
  CronframeT = Struct("cronframe", "freq floor squelch cronstr cronlen channels gain")
  return CronframeT(None, None, None, "", 0, [])

def channel():
  ChannelT = Struct("channel", "freq bw cont")
  return ChannelT(None, None, 0)

