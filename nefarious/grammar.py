
from .types import *
from .lex import Word, Lexer
from .parser import Grammar, Rule, grammar_parse

# two kinds of factories--
# * a Function pointer. From which, we build an AST node. This gets evaluated at runtime.
#
# * But! Sometimes we want to evaluate a rule at compile-time.
#   So, we invent Macros. These are just functions which are evaluated at
#   compile-time, and return a piece of AST.

# TODO common base class for Function and Macro
class Function(Tree):
    def __init__(self, debug_name):
        assert isinstance(debug_name, str)
        self.debug_name = debug_name
        self.body = None
        self.args = []

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
        grammar.save()

    def exit(self, children, type_):
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
        indent = " "
        is_lines = self.func == PROGRAM or self.func == BLOCK
        sep = "\n" if is_lines else " "
        inner = sep.join([a.sexpr() for a in self.args])
        if is_lines:
            inner = indent + ("\n" + indent).join(inner.split("\n"))
        return "(" + self.func.sexpr() + sep + inner + ")"
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

LINES = Function('Lines') # Internal

Internal.SEP = Internal.get("SEP")
grammar.add(Internal.SEP, [], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.WS], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.NL], Null)

grammar.add(Seq.get(Line), [], EmptyList(LINES))
grammar.add(Seq.get(Line), [Line], StartList(LINES))
grammar.add(Seq.get(Line), [Seq.get(Line), Internal.SEP, Line], ContinueList(LINES))


# Blocks
BLOCK = Function('block')
@singleton
class Block(Macro):
    def build(self, values, type_):
        values[2].func = BLOCK
        return values[2]
grammar.add(Type.BLOCK, [Word.word("{"), Internal.SEP, Seq.get(Line), Internal.SEP, Word.word("}")], Block)


# Program
PROGRAM = Function('program')
@singleton
class Program(Macro):
    def build(self, values, type_):
        return Call(PROGRAM, type_, values[1].args)
grammar.add(Type.PROGRAM, [Internal.SEP, Seq.get(Line), Internal.SEP], Program)


# Identifiers

Iden = Internal.get('Iden')

grammar.add(Iden, [Word.WORD], Identity)
grammar.add(Iden, [Word.PUNC], Identity)
grammar.add(Iden, [Word.WS_NOT_NULL], Identity)
# TODO Word.DIGITS


# Definitions

Spec = Internal.get('Spec')

ARG = Function("arg")

@singleton
class ArgSpec(Macro):
    def build(self, values, type_):
        type_, _, name = values
        assert isinstance(name, Word)
        assert isinstance(type_, Type)
        return Call(ARG, type_, [type_, name])
grammar.add(Spec, [Type.TYPE, Word.word(":"), Word.WORD], ArgSpec)

grammar.add(Spec, [Iden], Identity)

SPEC = Function('spec')
grammar.add(Seq.get(Spec), [Spec], StartList(SPEC))
grammar.add(Seq.get(Spec), [Seq.get(Spec), Spec], ContinueList(SPEC))

class Arg(Tree):
    def __init__(self, type_, debug_name):
        assert isinstance(type_, Type)
        assert isinstance(debug_name, str)
        self.type = type_
        self.debug_name = debug_name

    def __repr__(self):
        return "Arg({!r}, {!r})".format(self.type, self.debug_name)

    def sexpr(self):
        return "(arg " + self.debug_name + ")"


DEFINE = Function('define')

@singleton
class Define(Macro):
    current_definitions = []

    def _is_arg(self, word):
        return isinstance(word, Call) and word.func == ARG

    def _get_spec(self, values):
        spec = values[2]
        assert spec.func == SPEC
        symbols = list(spec.args)
        return symbols

    def enter(self, values, type_):
        grammar.save()
        spec = self._get_spec(values)

        # Build name
        debug_name = ""
        for s in spec:
            if self._is_arg(s):
                debug_name += s.args[0].name
            elif s == Word.WS:
                debug_name += "_"
            elif isinstance(s, Word):
                debug_name += s.value
            else:
                assert False, s
        func = Function(debug_name)
        Define.current_definitions.append(func)

        # Define arguments
        args = func.args
        for word in spec:
            if self._is_arg(word):
                type_, name = word.args
                index = len(args)
                assert isinstance(name, Word)
                arg = Arg(type_, name.value)
                grammar.add(type_, [name], Literal(arg)) # TODO arg macro
                args.append(arg)

        # Add internal (recursive) rule
        symbols = [(s.args[0] if self._is_arg(s) else s) for s in spec]
        arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
        grammar.add(Generic.ALPHA, symbols, CallMacro(func, arg_indexes))

    def exit(self, values, type_):
        grammar.restore()
        spec = self._get_spec(values)
        func = Define.current_definitions[-1]

        # Type check
        body = values[-1]
        assert body.func == BLOCK
        type_ = body.args[-1].type
        # TODO empty functions
        # TODO check unification with `func` calls in body

        # Define rule
        symbols = [(s.args[0] if self._is_arg(s) else s) for s in spec]
        arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
        grammar.add(type_, symbols, CallMacro(func, arg_indexes))

    def build(self, values, type_):
        func = Define.current_definitions.pop()
        args = Call(LIST, List.get(Type.ANY), func.args)
        return Call(DEFINE, type_, [func, args, values[4]])

grammar.add(Line, [Word.word("define"), Word.WS, Seq.get(Spec), Word.WS, Type.BLOCK], Define)


# Let

class Name(Tree):
    # TODO merge with Arg?
    # TODO merge with Function?
    def __init__(self, type_, debug_name):
        assert isinstance(type_, Type)
        assert isinstance(debug_name, str)
        self.type = type_
        self.debug_name = debug_name

    def __repr__(self):
        return "Name({!r}, {!r})".format(self.type, self.debug_name)

    def sexpr(self):
        return self.debug_name

LET = Function("let")

@singleton
class Let(Macro):
    def build(self, values, type_):
        value = values[6]

        identifier = values[2].args
        name = ""
        for iden in identifier:
            assert isinstance(iden, Word)
            if iden == Word.WS:
                name += "_"
            else:
                name += iden.value
        var = Name(value.type, name)

        grammar.add(value.type, identifier, Literal(var))

        return Call(LET, type_, [var, value])

IDEN = Function('iden')
grammar.add(Seq.get(Iden), [Iden], StartList(IDEN))
grammar.add(Seq.get(Iden), [Seq.get(Iden), Iden], ContinueList(IDEN))

grammar.add(Line, [
    Word.word("let"), Word.WS, Seq.get(Iden), Word.WS, Word.word("="), Word.WS, Type.ANY
], Let)



# Built-ins.

class Value(Tree):
    def __init__(self, type_, value):
        assert isinstance(value, str)
        self.type = type_
        self.value = value

    def sexpr(self):
        assert isinstance(self.value, str)
        return self.value

# Int

Int = Type.get('Int')
class W_Int(Value):
    type = Int
    def __init__(self, value):
        assert isinstance(value, int)
        self.value = value
    def sexpr(self):
        return str(self.value)

@singleton
class ParseInt(Macro):
    def build(self, values, type_):
        assert type_ == Int
        digits, = values
        assert isinstance(digits, Word)
        return W_Int(int(digits.value))
grammar.add(Int, [Word.DIGITS], ParseInt)

# Decimal

#grammar.add(Int, [Word.DIGITS, Word.word("."), Word.DIGITS], ParseDecimal)
# TODO W_Decimal

Text = Type.get('Text')
Bool = Type.get('Bool')
add_type(Int)
add_type(Text)
add_type(Bool)



# Language stuff.

PLUS = Function("+")
SUB = Function("-")
grammar.add(Int, [Int, Word.WS, Word.word("+"), Word.WS, Int], CallMacro(PLUS, [0, 4])).priority = grammar.add(Int, [Int, Word.WS, Word.word("-"), Word.WS, Int], CallMacro(SUB, [0, 4])).priority

LT = Function("<")
grammar.add(Bool, [Int, Word.WS, Word.word("<"), Word.WS, Int], CallMacro(LT, [0, 4]))

IF = Function("if")
#grammar.add(Generic.ALPHA, [Generic.ALPHA, Word.WS, Word.word("if"), Word.WS, Bool, Word.WS, Word.word("else"), Word.WS, Generic.ALPHA], CallMacro(IF, [4, 0, 8]))
# TODO: don't seem to support left-recursive generics.
grammar.add(Generic.ALPHA, [Word.word("if"), Word.WS, Bool, Word.WS, Word.word("then"), Word.WS, Generic.ALPHA, Word.WS, Word.word("else"), Word.WS, Generic.ALPHA], CallMacro(IF, [2, 6, 10]))

# TODO consider binding user functions with lower precedence...


def parse(source, debug=False):
    return grammar_parse(source, grammar, debug)

