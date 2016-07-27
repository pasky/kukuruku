from libutil import Struct

""" Definition of scan frames.

    From each .conf file, one (single frequency) or more (range) frames are generated.
    The scanner then one frame a time (pseudorandomly or based on cronstring), tunes to
    its frequency and records/detects peaks.

    Each frame contains freq, floor, stickactivity, stick, silencegap, sql and gain.
    They are the same as in config.
    Then, they contain list of channels.

    Additionally, cronframe contains "cron" string.
"""

def scanframe():
  ScanframeT = Struct("scanframe", "freq floor stickactivity stick silencegap sql gain channels")
  return ScanframeT(0, 0, False, 0, 0, 0, 0, [])

def cronframe():
  CronframeT = Struct("cronframe", "freq floor stickactivity stick silencegap sql gain channels cron")
  return CronframeT(0, 0, False, 0, 0, 0, 0, [], "")

def channel():
  """ Definition of one channel generated from the [ChannelName] section in .conf file """

  ChannelT = Struct("channel", "freq bw taps pipe")
  return ChannelT(0, 0, [], None)

