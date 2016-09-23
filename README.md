_Nefarious Scheme_.
===================

A programming language with:

* **mutable syntax**.
* an efficient yet dynamic parser.
* function _syntax_ rather than function names.
* equivalence between types and CFG non-terminals.
* lexical scope.
* CFG rule priority: newest takes precedence [so shadowing works!].
* an incremental hybrid GC.
* ~~a fast tracing JIT bytecode VM (based on PyPy).~~ [not yet—compilers are hard!]

Written in RPython; compiles to native code (via C), using the [RPython
toolchain](https://rpython.rtfd.io/). But it can also run on top of a standard
Python interpreter (albeit slower).

**_Work in progress._**

