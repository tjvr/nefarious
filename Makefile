PYPY_EXECUTABLE := $(shell which pypy)

ifeq ($(PYPY_EXECUTABLE),)
RUNINTERP = python
else
RUNINTERP = $(PYPY_EXECUTABLE)
endif

nfs: pypy nefarious/parser.py nefarious/nefarious.py
	$(RUNINTERP) pypy/rpython/bin/rpython --gc=incminimark --output=nfs nefarious/nefarious.py
	# -Ojit --jit-backend=x86 --translation-jit
	# --cc=afl-clang

nfs-interp:
	$(RUNINTERP) nefarious/nefarious.py bar.txt

pypy:
	echo "Downloading PyPy..."
	hg clone https://bitbucket.org/pypy/pypy

test:
	$(RUNINTERP) -m unittest --buffer tests

