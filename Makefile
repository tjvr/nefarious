
PYPY_SOURCE := "pypy2-v5.4.1-src"
PYPY_EXECUTABLE := $(shell which pypy)

CPYTHON := $(shell which python2)
ifeq ($(CPYTHON),)
	CPYTHON = $(shell which python)
endif

ifeq ($(PYPY_EXECUTABLE),)
	TESTINTERP := $(CPYTHON)
	PYNAME := "CPython"
else
	TESTINTERP := $(PYPY_EXECUTABLE)
	PYNAME := "PyPy"
endif

# translation is supposed to be faster under pypy
# but on my Mac/Linux machines, nefarious translates faster under CPython!
BUILDINTERP = $(CPYTHON)

#------------------------------------------------------------------------------

all:
	make test && make nfs

nfs: pypy \
		nefarious/lex.py \
		nefarious/types.py \
		nefarious/parser.py \
		nefarious/grammar.py \
		nefarious/compile.py \
		nefarious/nefarious.py
	@echo ============================================================
	@echo Using CPython: $(CPYTHON)
	@echo Invoking RPython toolchain to build executable...
	@echo
	$(BUILDINTERP) pypy/rpython/bin/rpython --gc=incminimark --output=nfs goal.py
	@echo
	@echo "Wrote 'nfs'"
	@echo ============================================================
	make test-nfs
.TODO:
	# -Ojit --jit-backend=x86 --translation-jit
	#@rem --cc=afl-clang

nfs-interp:
	$(TESTINTERP) -m nefarious bar.txt

test:
	@echo Running tests \(using $(PYNAME)\)...
	$(TESTINTERP) -m unittest --buffer tests
	@echo Tests passed!
test-cpython:
	@echo Running tests \(force CPython\)...
	$(CPYTHON) -m unittest --buffer tests
test-nfs:
	@echo Testing compiled binary...
	$(TESTINTERP) -m unittest --buffer tests.compiled

# RPython toolchain is required to build nfs executable.
pypy.zip:
	@echo Downloading PyPy source $(PYPY_SOURCE)...
	curl -L https://bitbucket.org/pypy/pypy/downloads/$(PYPY_SOURCE).zip > pypy.zip
pypy: pypy.zip
	@echo Unzipping $(PYPY_SOURCE)...
	rm -rf pypy
	unzip -qn pypy.zip
	mv $(PYPY_SOURCE)/ pypy
	touch pypy

clean:
	rm nfs
reallyclean: clean
	rm pypy.zip
	rm -r pypy/

#------------------------------------------------------------------------------
.PHONY: all nfs-interp test test-nfs clean reallyclean

