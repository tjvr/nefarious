PYPY_EXECUTABLE := $(shell which pypy)

ifeq ($(PYPY_EXECUTABLE),)
RUNINTERP = python
else
RUNINTERP = $(PYPY_EXECUTABLE)
endif

nfs: test pypy nefarious/parser.py nefarious/nefarious.py
	$(RUNINTERP) pypy/rpython/bin/rpython --gc=incminimark --output=nfs goal.py
	# -Ojit --jit-backend=x86 --translation-jit
	# --cc=afl-clang

nfs-interp:
	$(RUNINTERP) -m nefarious bar.txt

pypy:
	echo "Downloading PyPy source..."
	hg clone https://bitbucket.org/pypy/pypy

test:
	$(RUNINTERP) -m unittest --buffer tests

test-nfs:
	# test compiled binary
	$(RUNINTERP) -m unittest --buffer tests.compiled

