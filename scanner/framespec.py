from libutil import Struct

def scanframe():
  ScanframeT = Struct("scanframe", "freq floor squelch channels gain stickactivity pipe")
  return ScanframeT(None, None, None, [], 0, False, None)

def cronframe():
  CronframeT = Struct("cronframe", "freq floor squelch cronstr cronlen channels gain stickactivity pipe")
  return CronframeT(None, None, None, "", 0, [], 0, False, None)

def channel():
  ChannelT = Struct("channel", "freq bw cont")
  return ChannelT(None, None, 0)

