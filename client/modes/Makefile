CC = grcc
CFLAGS = -d .

all: modes

MODES = tetrapol.py tetra.py nfm.py mfm.py wfm.py raw.py

%.py: %.grc
	$(CC) $(CFLAGS) $<

modes: $(MODES)

clean:
	rm -fr *.py

