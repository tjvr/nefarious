
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

    def call_immediate(self, children):
        assert self.body is not None
        # TODO

class Macro(Function):
    def build(self, children, type_):
        return self.call_immediate(children)

    def enter(self, children, type_):
        global grammar
        grammar.save()

    def exit(self, children, type_):
        global grammar
        grammar.restore()

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

    def __repr__(self):
        return "<Call {!r} {!r}>".format(self.func.debug_name, self.args)

    def sexpr(self):
        return "(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"
        #return self.type.sexpr() + ":(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"

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

class Select(Macro):
    def __init__(self, index):
        self.index = index
    def build(self, values, type_):
        return values[self.index]


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

class EmptyList(Macro):
    def __init__(self, call):
        self.call = call
    def build(self, values, type_):
        return Call(self.call, type_, [])

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

@singleton
class ListTypeMacro(Macro):
    def build(self, values, type_):
        return List.get(values[4])

grammar.add(Type.TYPE, [Word.word("("), Word.WS, Word.word("List"), Word.WS, Type.TYPE, Word.WS, Word.word(")")], ListTypeMacro)


# Lines

Line = Type.get('Line')
grammar.add(Line, [Type.ANY], Identity)
grammar.add(Line, [Type.ANY], Identity)

LINES = Function('lines')

Internal.SEP = Internal.get("SEP")
grammar.add(Internal.SEP, [], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.WS], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.NL], Null)

grammar.add(Seq.get(Line), [], EmptyList(LINES))
grammar.add(Seq.get(Line), [Line], StartList(LINES))
grammar.add(Seq.get(Line), [Seq.get(Line), Internal.SEP, Line], ContinueList(LINES))


# Blocks
@singleton
class Block(Macro):
    def build(self, values, type_):
        return values[2]
grammar.add(Type.BLOCK, [Word.word("{"), Internal.SEP, Seq.get(Line), Internal.SEP, Word.word("}")], Block)


# Program
grammar.add(Type.PROGRAM, [Internal.SEP, Seq.get(Line), Internal.SEP], Select(1))


# Definitions

Spec = Internal.get('Spec')

grammar.add(Spec, [Word.WORD], Identity)

ARG = Function("arg")

@singleton
class ArgSpec(Macro):
    def build(self, values, type_):
        type_, _, name = values
        assert isinstance(name, Word)
        assert isinstance(type_, Type)
        return Call(ARG, type_, [type_, name])
grammar.add(Spec, [Type.TYPE, Word.word(":"), Word.WORD], ArgSpec)

grammar.add(Seq.get(Spec), [Spec], StartList(LIST))
grammar.add(Seq.get(Spec), [Seq.get(Spec), Word.WS, Spec], ContinueList(LIST))

DEFINE = Function('define')

@singleton
class Define(Macro):
    def enter(self, values, type_):
        global grammar
        grammar.save()

        # Define arguments
        spec = values[2]
        assert spec.func == LIST
        for word in spec.args:
            if isinstance(word, Call) and word.func == ARG:
                type_, name = word.args
                grammar.add(type_, [name], Identity) # TODO arg macro

    def exit(self, values, type_):
        global grammar
        grammar.restore()

    def build(self, values, type_):
        return Call(DEFINE, type_, [values[2], values[4]])

grammar.add(Line, [Word.word("define"), Word.WS, Seq.get(Spec), Word.WS, Type.BLOCK], Define)




# Built-ins.

Int = Type.get('Int')
Text = Type.get('Text')
Bool = Type.get('Bool')
add_type(Int)
add_type(Text)
add_type(Bool)

grammar.add(Int, [Word.word("123")], Identity)


def parse(source, debug=False):
    return grammar_parse(source, grammar, debug)

