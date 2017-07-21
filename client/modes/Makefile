CC = grcc
CFLAGS = -d .

all: modes

MODES = tetrapol.py tetra.py nfm.py mfm.py wfm.py raw.py sonde_sgp.py

%.py: %.grc
	$(CC) $(CFLAGS) $<

modes: $(MODES)

clean:
	rm -fr *.py

