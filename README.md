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

Overview
--------

Nefarious is a text-based programming language. It has mutable syntax: the language grammar can be extend at runtime.

The idea is to do away with DSLs and operator overloading and so on, and just have fully general function syntax.

Here's a quick (and poorly chosen) example:

	define Int:a + Int:b { return (INT_ADD a b) }
	define Int:a - Int:b { return (INT_SUB a b) }
	define if Bool:test then Block:tv else Block:fv { ... }

	define fib Int:n {
		if n < 2 then { return 1 } else { return fib (n - 1) + fib (n - 2) }
	}

It has a very simple tokenisation stage: it separates out newlines, whitespace, individual punctuation characters, and strings of digits; anything that's left tokenises as a WORD.

I use a sophisticated Earley parser; this allows me to be flexible and extend the grammar during parsing.

When a variable declaration is encountered, eg:
```
	let x = 42
```
the parser adds a new production `Int -> x` to the grammar.

Blocks `{ }` have their own scope. When we enter a block, we save the current grammar onto a stack; upon exiting the block we pop its rules. In this way the parser gives us lexical scope and variable shadowing for free.

Functions are defined not with *names*, but with a list of *symbols*. (This gets converted into a CFG rule.) eg:
```
    define fib Int:n { ... }
```

The function `fib _` has one argument slot, named `n`, of type `Int`.

Upon entering the function's body, the parser pushes its arguments onto the stack; like we did variables.

After parsing the entire body, the function is type-checked, and a new rule added to the grammar; in this case `Int -> 'fib' Int`.

In this way, the parser builds up a Scheme-like AST for the whole program file.

Just like Scheme, we could support macros which are evaluated at compile-time (after parse-time).

To make all this manageable, we enforce an equivalence between non-terminals (in the CFG) and types (in the language's type system). So the LHS of a production is always its type: Int/Bool/Text/whatever. There are special types for Line and Block and Program.

This is done to help resolve ambiguity; there's no point accepting parses that won't type-check, when there are other parses that will.

Although moving type-checking into the parser may turn out to be horrible to use in practice!

The other tool for resolving ambiguity is ordered choice; if two different productions result in the same non-terminal, the one defined most recently always wins. (This is why shadowing works.)

There's some extra magic to handle parametric types/rules — eg `T -> if Bool then T else T`, or `List T -> T ',' T` [Except for left-recursive parametrics, eg. T -> T, which turns out to be iffy.]

This is all then compiled to bytecode for a custom VM. My plan is for the "core" language to just define rules for emitting the bytecodes; defining labels & jumps; and handling functions and name bindings; and then everything else can be implemented in the language itself, including control flow and all the built-in syntax.

The idea, after all, was to do away with DSLs! I imagine there would be standard "preambles" which define a nice language to work with. Maybe even specialised ones for different
domains (science, math)?

I've omitted a few details (eg. upvars, optional whitespace), but this overview is too long as it is!

There are a range of fun extensions to the language and/or compiler: I could add an optimising compiler to the VM, and do flow analysis/SSA. Implementing closures properly could be fun. And the language would rather benefit from unevaluated argument types: `define while (Uneval Bool):test do Block:body`?



Install
-------

**Ubuntu**: for making the JIT (`make nfsj`), you'll need to run:

    sudo apt-get install libffi-dev

