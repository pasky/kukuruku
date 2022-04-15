CC = grcc
CFLAGS = -o .

all: modes

MODES = mfm.py tetrapol.py tetra.py nfm.py mfm.py wfm.py raw.py sonde_sgp.py


%.py: %.grc
	$(CC) $(CFLAGS) $<

modes: $(MODES)

clean:
	rm -fr *.py

