PYPY_EXECUTABLE := $(shell which pypy)
PYPY_SOURCE := "pypy2-v5.4.1-src"

ifeq ($(PYPY_EXECUTABLE),)
RUNINTERP = python
else
RUNINTERP = $(PYPY_EXECUTABLE)
endif

all:
	make test && make nfs

nfs: pypy \
		nefarious/lex.py \
		nefarious/types.py \
		nefarious/parser.py \
		nefarious/grammar.py \
		nefarious/nefarious.py
	$(RUNINTERP) pypy/rpython/bin/rpython --gc=incminimark --output=nfs goal.py
	# -Ojit --jit-backend=x86 --translation-jit
	# --cc=afl-clang
	make test-nfs

nfs-interp:
	$(RUNINTERP) -m nefarious bar.txt

test:
	$(RUNINTERP) -m unittest --buffer tests
test-nfs:
	# Test compiled binary.
	$(RUNINTERP) -m unittest --buffer tests.compiled

# RPython toolchain is required to build nfs executable.
pypy.zip:
	echo "Downloading PyPy source $(PYPY_SOURCE)..."
	curl -L https://bitbucket.org/pypy/pypy/downloads/$(PYPY_SOURCE).zip > pypy.zip
pypy: pypy.zip
	echo "Unzipping $(PYPY_SOURCE)..."
	rm -rf pypy
	unzip -qn pypy.zip
	mv $(PYPY_SOURCE)/ pypy
	touch pypy

clean:
	rm nfs
reallyclean: clean
	rm pypy.zip
	rm -r pypy/

