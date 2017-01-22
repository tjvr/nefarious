
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

nfs: pypy src
	@echo ============================================================
	@echo Using CPython: $(CPYTHON)
	@echo Invoking RPython toolchain to build executable...
	@echo
	$(BUILDINTERP) pypy/rpython/bin/rpython --gc=incminimark --output=nfs goal.py
	@echo
	@echo "Wrote 'nfs'"
	@echo ============================================================
	make test-nfs

nfsj: pypy src
	@echo ============================================================
	@echo Using CPython: $(CPYTHON)
	@echo Invoking RPython toolchain to build executable WITH JIT...
	@echo
	$(BUILDINTERP) pypy/rpython/bin/rpython --gc=incminimark --output=nfsj --translation-jit goal.py
	# -Ojit --jit-backend=x86 --translation-jit goal.py
	@echo "Wrote 'nfsj'"
	@echo ============================================================

src: pypy \
		nefarious/lex.py \
		nefarious/types.py \
		nefarious/parser.py \
		nefarious/values.py \
		nefarious/tree.py \
		nefarious/builtins.py \
		nefarious/grammar.py
.TODO:
	#@rem --cc=afl-clang

nfs-interp:
	$(TESTINTERP) -m nefarious bar.txt

test:
	@echo Running tests \(using $(CPYTHON)\)...
	$(BUILDINTERP) -m unittest --buffer tests
	@echo Tests passed!
test-pypy:
	@echo Running tests \(force PyPy\)...
	$(PYPY_EXECUTABLE) -m unittest --buffer tests
test-nfs:
	@echo Testing compiled binary...
	$(BUILDINTERP) -m unittest --buffer tests.compiled

# RPython toolchain is required to build nfs executable.
pypy.zip:
	@echo Downloading PyPy source $(PYPY_SOURCE)...
	curl -L https://bitbucket.org/pypy/pypy/downloads/$(PYPY_SOURCE).zip > pypy.zip
pypy: pypy.zip
	@echo Unzipping $(PYPY_SOURCE)...
	rm -rf pypy
	unzip -qn pypy.zip
	mv $(PYPY_SOURCE) pypy
	touch pypy

clean:
	rm nfs || echo
	rm nfsj || echo
reallyclean: clean
	rm pypy.zip || echo
	rm -r pypy/ || echo

#------------------------------------------------------------------------------
.PHONY: all nfs-interp test test-nfs clean reallyclean src

