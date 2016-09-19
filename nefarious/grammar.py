
from .types import *
from .lex import Word, Lexer
from .parser import Grammar, Rule, grammar_parse

# two kinds of factories--
# * a Function pointer. From which, we build an AST node. This gets evaluated at runtime.
#
# * But! Sometimes we want to evaluate a rule at compile-time.
#   So, we invent Macros. These are just functions which are evaluated at
#   compile-time, and return a piece of AST.

class Function:
    def __init__(self, debug_name):
        assert isinstance(debug_name, str)
        self.debug_name = debug_name
        self.body = None

    def sexpr(self):
        return self.debug_name

    def set_body(self, body):
        assert isinstance(body, Body)
        self.body = body

    def build(self, children, type_):
        return Call(self, type_, children)

    def call_immediate(self, children):
        assert self.body is not None
        # TODO

class Macro(Function):
    def build(self, children, type_):
        return self.call_immediate(children)

    def sexpr(self):
        assert False # macros should never be in the AST!

class Call(Tree):
    def __init__(self, func, type_, args):
        assert isinstance(func, Function)
        assert isinstance(type_, Type)
        assert isinstance(args, list)
        for arg in args:
            assert isinstance(arg, Tree)
        self.func = func
        self.type = type_
        self.args = args

    def sexpr(self):
        #return "(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"
        return self.type.sexpr() + ":(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"

class CallMacro(Macro):
    def __init__(self, call, arg_indexes):
        assert isinstance(call, Function) and not isinstance(call, Macro)
        self.call = call
        self.arg_indexes = arg_indexes

    def build(self, values, type_):
        args = [values[i] for i in self.arg_indexes]
        return Call(self.call, type_, args)



grammar = Grammar()

def singleton(cls):
    return cls(cls.__name__)

@singleton
class Identity(Macro):
    def build(self, values, type_):
        assert len(values) == 1
        return values[0]


# Whitespace
@singleton
class Null(Macro):
    def build(self, values, type_):
        return Word.NULL_WS
# whitespace is always optional, but only permitted if it appears in the defition.
# eg. "Int <> Int" would not allow a space between < and >.
grammar.add(Word.WS, [], Null)


# List -- After all, this is "Nefarious Scheme"
LIST = Function('list')

class StartList(Macro):
    def __init__(self, call):
        self.call = call
    def build(self, values, type_):
        return Call(self.call, type_, [values[0]])

class PairList(Macro):
    def __init__(self, call):
        self.call = call
    def build(self, values, type_):
        return Call(self.call, type_, [values[0], values[-1]])

class ContinueList(Macro):
    def __init__(self, call):
        self.call = call
    def build(self, values, type_):
        list_ = values[0]
        assert isinstance(list_, Call) and list_.func is self.call
        list_.args.append(values[-1])
        return list_

# Generic lists
ALPHA = Generic.ALPHA
grammar.add(List.get(ALPHA), [ALPHA, Word.WS, Word.word(","), Word.WS, ALPHA], PairList(LIST))
grammar.add(List.get(ALPHA), [List.get(ALPHA), Word.WS, Word.word(","), Word.WS, ALPHA], ContinueList(LIST))

# TODO revisit this... --require square brackets?


# Parentheses

@singleton
class Parens(Macro):
    def build(self, values, type_):
        child = values[2]
        return child
grammar.add(Generic.get(1), [Word.word("("), Word.WS, Generic.get(1), Word.WS, Word.word(")")], Parens)


# Program

Line = Type.get('Line')

grammar.add(Type.PROGRAM, [Line, Word.NL], Identity)

# TODO lines
grammar.add(Line, [Type.ANY], Identity)


# Types

class Literal(Macro):
    def __init__(self, value):
        self.value = value
    def build(self, values, type_):
        return self.value

def add_type(type_):
    name = type_._str()
    assert len(name.split(" ")) == 1
    grammar.add(Type.TYPE, [Word.word(name)], Literal(type_))


# Define -- the most important function (!)

DEFINE = Function('define')
Spec = Internal.get('Spec')
DefSpec = Internal.get('DefSpec')

# We want to--
# - allow for scoping the inside of blocks.
#   so eg. an `sql _` statement that accepts a block -- `sql { select * from ... }`
#
# when *does* evaluation happen?
#
# it would be fine if evaluation/scoping was hard-bound to { }...

@singleton
class Define(Macro):
    def build(self, values, type_):
        return Call(DEFINE, type_, [values[2]])

grammar.add(Line, [
    Word.word('define'), Word.WS, DefSpec, Word.WS, Word.word("{"),
], Define)

WORD = Function('word')
@singleton
class WordMacro(Macro):
    def build(self, values, type_):
        return Call(WORD, type_, values)
grammar.add(Spec, [Word.WORD], WordMacro)

ARG = Function('arg')
@singleton
class ArgMacro(Macro):
    def build(self, values, type_):
        return Call(ARG, type_, values)
grammar.add(Spec, [Type.TYPE], ArgMacro)

grammar.add(Seq.get(Spec), [Spec], StartList(LIST))
grammar.add(Seq.get(Spec), [Seq.get(Spec), Word.WS, Spec], ContinueList(LIST))

@singleton
class DefSpecMacro(Macro):
    def build(self, values, type_):
        assert values[0].func == LIST
        values = values[0].args

        symbols = []
        names = []
        for v in values:
            if v.func == ARG:
                names.append(v.args[0])
                symbols.append(v.args[0])
            elif v.func == WORD:
                symbols.append(v.args[0])

        symbols = Call(LIST, List.get(Type.get('Tag')), symbols)
        names = Call(LIST, List.get(Text), names)
        return Call(DEFINE, type_, [symbols, names])

grammar.add(DefSpec, [Seq.get(Spec)], DefSpecMacro)


# Built-ins.

Int = Type.get('Int')
Text = Type.get('Text')
Bool = Type.get('Bool')
add_type(Int)
add_type(Text)
add_type(Bool)


def parse(source, debug=False):
    return grammar_parse(source, grammar, debug)

