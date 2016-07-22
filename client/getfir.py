from gnuradio.filter import firdes

def getfir(samplerate, filtertype, bw, transition, maxtaps):
  """ Design a FIR lowpass.

      The filter will have samplerate/bw passband.

      filtertype -- string "window" or "rcos"
        window -- design a Hamming window lowpass
        rcos -- design a Root Raised Cosine lowpass https://en.wikipedia.org/wiki/Root-raised-cosine_filter

        For some digital protocols, like Tetra, rcos filter minimizes intersymbol interference.
        For analog modulations it is probably insignificant.

      transition -- adjusts order of the filter
        For "window" type filter, it is the transition band, and GnuRadio documentation
          does not tell you much more about it
          http://gnuradio.org/doc/doxygen/classgr_1_1filter_1_1firdes.html#a772eb5c542093d65518a6d721483aace
        For "rcos" filter, it is the order of the filter (number of taps)

      maxtaps -- do not exceed this number of taps
  """

  coefs = None

  if filtertype not in ["hamming", "rcos"]:
    print("Unknown filter type %s, defaulting to hamming"%xl.filtertype)
    filtertype = "hamming"

  if filtertype == "hamming":
    while True:
      coefs = firdes.low_pass(1, samplerate, bw, transition, firdes.WIN_HAMMING)
      if len(coefs) < maxtaps:
        break
      print("transition %f yields too long filter (%i)"%(transition, len(coefs)))
      transition += 1
      transition *= 1.2
      print("trying transition %f"%transition)
  elif filtertype == "rcos":
    if transition > maxtaps:
      print("The requested raised cosine filter of len %i is too long. Limiting to %i."%(transition, maxtaps))
      transition = maxtaps
    coefs = firdes.root_raised_cosine(1, samplerate, bw, 0.35, transition)
  return coefs


