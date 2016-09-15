PYPY_EXECUTABLE := $(shell which pypy)

ifeq ($(PYPY_EXECUTABLE),)
RUNINTERP = python
else
RUNINTERP = $(PYPY_EXECUTABLE)
endif

nfs: nefarious/parser.py nefarious/nefarious.py
	$(RUNINTERP) rpython/bin/rpython --gc=incminimark --output=nfs nefarious/nefarious.py
	# -Ojit --jit-backend=x86 --translation-jit
	# --cc=afl-clang

nfs-interp:
	$(RUNINTERP) nefarious/nefarious.py bar.txt

