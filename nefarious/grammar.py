
from .types import *
from .lex import Word, Lexer


class Name(Tree):
    """Symbol. Compared by identity, not value, so shadowing works."""
    def __init__(self, type_, name):
        assert isinstance(type_, Type)
        assert isinstance(name, str)
        self.type = type_
        self.name = name # String name really is just a debugging aid

    def __repr__(self):
        return "Name({!r}, {!r})".format(self.type, self.name)

    def sexpr(self):
        return self.name.replace(" ", "_")


class Call(Tree):
    def __init__(self, func, type_, args):
        assert isinstance(func, Name)
        assert func.type == Type.FUNC
        assert isinstance(type_, Type)
        assert isinstance(args, list)
        for arg in args:
            assert isinstance(arg, Tree)
        self.func = func
        self.type = type_
        self.args = args

    def __repr__(self):
        return "<Call {!r} {!r}>".format(self.func.name, self.args)

    def sexpr(self):
        indent = " "
        is_lines = self.func == PROGRAM or self.func == BLOCK
        sep = "\n" if is_lines else " "
        inner = sep.join([a.sexpr() for a in self.args])
        if is_lines:
            inner = indent + ("\n" + indent).join(inner.split("\n"))
        return "(" + self.func.sexpr() + sep + inner + ")"
        #return self.type.sexpr() + ":(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"


class Value(Tree):
    def __init__(self, type_, value):
        assert isinstance(value, str)
        self.type = type_
        self.value = value

    def sexpr(self):
        assert isinstance(self.value, str)
        return self.value


def Function(name):
    return Name(Type.FUNC, name)


class Error(Tree):
    def __init__(self, message):
        self.message = message


#---------------

from .parser import Grammar, Rule, grammar_parse

def between(thing, symbols):
    assert len(symbols)
    out = []
    out.append(symbols[0])
    for tag in symbols[1:]:
        out.append(thing)
        out.append(tag)
    return out

def ws(symbols):
    return between(Word.WS, symbols)

def ws_not_null(symbols):
    return between(Word.WS_NOT_NULL, symbols)


class Macro:
    # * Sometimes we want to evaluate a rule at compile-time.
    #   So, we invent Macros. These are just functions which are evaluated at
    #   compile-time, and return a piece of AST.

    def build(self, children, type_):
        raise NotImplementedError

    def enter(self, children, type_):
        grammar.save()

    def exit(self, children, type_):
        grammar.restore()

class CallMacro(Macro):
    def __init__(self, call, arg_indexes):
        assert isinstance(call, Name)
        self.call = call
        self.arg_indexes = arg_indexes

    def build(self, values, type_):
        args = [values[i] for i in self.arg_indexes]
        return Call(self.call, type_, args)

# TODO CustomMacros
#    return self.call_immediate(children)


grammar = Grammar()

def singleton(cls):
    return cls()

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
grammar.add(List.get(ALPHA), ws([ALPHA, Word.word(","), ALPHA]), PairList(LIST))
grammar.add(List.get(ALPHA), ws([List.get(ALPHA), Word.word(","), ALPHA]), ContinueList(LIST))

# TODO revisit this... --require square brackets?


# Parentheses

@singleton
class Parens(Macro):
    def build(self, values, type_):
        child = values[2]
        return child
grammar.add(ALPHA, ws([Word.word("("), ALPHA, Word.word(")")]), Parens)


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

grammar.add(Type.TYPE, ws([Word.word("("), Word.word("List"), Type.TYPE, Word.word(")")]), ListTypeMacro)


# Lines

Line = Type.get('Line')
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
class BlockMacro(Macro):
    def build(self, values, type_):
        values[2].func = BLOCK
        return values[2]
grammar.add(Type.BLOCK, [Word.word("{"), Internal.SEP, Seq.get(Line), Internal.SEP, Word.word("}")], BlockMacro)

@singleton
class EmptyBlock(Macro):
    def build(self, values, type_):
        return Call(BLOCK, type_, [])
grammar.add(Type.BLOCK, [Word.word("{"), Word.word("}")], EmptyBlock)


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
# TODO Word.DIGITS ?


# Definitions

Spec = Internal.get('Spec')

ARG = Function("arg_spec")

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


DEFINE = Function('define')

@singleton
class Define(Macro):
    current_definitions = []
    current_definition_args = []

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
                type_ = s.args[0]
                assert isinstance(type_, Type)
                debug_name += type_.name
            else:
                assert isinstance(s, Word)
                debug_name += s.value
        func = Function(debug_name)
        Define.current_definitions.append(func)

        # Define arguments
        args = []
        for word in spec:
            if self._is_arg(word):
                type_, name = word.args
                index = len(args)
                assert isinstance(name, Word)
                arg = Name(type_, name.value)
                grammar.add(type_, [name], Literal(arg))
                args.append(arg)
        Define.current_definition_args.append(args)

        # Add internal (recursive) rule
        symbols = [(s.args[0] if self._is_arg(s) else s) for s in spec]
        arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
        grammar.add(ALPHA, symbols, CallMacro(func, arg_indexes))

    def exit(self, values, type_):
        grammar.restore()
        spec = self._get_spec(values)
        func = Define.current_definitions[-1]

        # Type check
        body = values[-1]
        assert body.func == BLOCK
        if len(body.args) == 0: # empty block
            type_ = Line # ??
        elif len(body.args) == 1:
            type_ = body.args[0].type
        else:
            # TODO walk AST for `return` statements
            type_ = body.args[-1].type
        # TODO check unification with `func` calls in body

        # Define rule
        symbols = [(s.args[0] if self._is_arg(s) else s) for s in spec]
        arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
        grammar.add(type_, symbols, CallMacro(func, arg_indexes))

    def build(self, values, type_):
        func = Define.current_definitions.pop()
        args = Define.current_definition_args.pop()
        return Call(DEFINE, type_, [func] + args + [values[4]])

grammar.add(Line, ws_not_null([
    Word.word("define"), Seq.get(Spec), Type.BLOCK,
]), Define)


# Let

LET = Function("let")

@singleton
class Let(Macro):
    def build(self, values, type_):
        value = values[6]

        identifier = values[2].args
        name = ""
        for iden in identifier:
            assert isinstance(iden, Word)
            name += iden.value

        var = Name(value.type, name)
        grammar.add(value.type, identifier, Literal(var))
        return Call(LET, type_, [var, value])

IDEN = Function('iden')
grammar.add(Seq.get(Iden), [Iden], StartList(IDEN))
grammar.add(Seq.get(Iden), [Seq.get(Iden), Iden], ContinueList(IDEN))

grammar.add(Line, ws_not_null([
    Word.word("let"), Seq.get(Iden), Word.word("="), Type.ANY
]), Let)


# Var

Var = Type.get("Var")
VAR = Function("var")

@singleton
class Declare(Macro):
    def build(self, values, type_):
        identifier = values[2].args
        name = ""
        for iden in identifier:
            assert isinstance(iden, Word)
            name += iden.value

        var = Name(Generic.ALPHA, name)
        grammar.add(Generic.ALPHA, identifier, Literal(var))
        grammar.add(Var, identifier, Literal(var))

        if len(values) > 3:
            value = values[7]
            return Call(VAR, type_, [var, value])
        else:
            return Call(VAR, type_, [var])

grammar.add(Line, [
    Word.word("var"), Word.WS_NOT_NULL, Seq.get(Iden)
], Declare)
grammar.add(Line, [
    Word.word("var"), Word.WS_NOT_NULL, Seq.get(Iden), Word.WS_NOT_NULL, Word.word(":"), Word.word("="), Word.WS_NOT_NULL, Type.ANY
], Declare)


SET = Function("set")

grammar.add(Line, [
    Var, Word.WS_NOT_NULL, Word.word(":"), Word.word("="), Word.WS_NOT_NULL, Type.ANY
], CallMacro(SET, [0, 5]))


# Return

RETURN = Function("return")

grammar.add(Line, [Word.word("return")], CallMacro(RETURN, []))

grammar.add(Line, ws_not_null([
    Word.word("return"), Type.ANY,
]), CallMacro(RETURN, [2]))

#grammar.add(Line, [
#    Word.word("RETURN"), Word.WS, Type.TYPE, Word.word(":"), Type.ANY,
#], ByteCode(Op.RETURN))



# Built-ins.

# Int

Int = Type.get('Int')
class W_Int(Value):
    type = Int
    def __init__(self, value):
        assert isinstance(value, int)
        self.value = value

    def __repr__(self):
        return 'W_Int({})'.format(str(self.value))

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


# Bool

Bool = Type.get('Bool')
class W_Bool(Value):
    type = Bool
    def __init__(self):
        assert False

    def __repr__(self):
        return 'W_Bool({})'.format(self.sexpr())

    @staticmethod
    def get(value):
        return W_Bool.TRUE if value else W_Bool.FALSE

class W_True(W_Bool):
    value = True
    def __init__(self): pass
    def sexpr(self): return 'yes'

class W_False(W_Bool):
    value = False
    def __init__(self): pass
    def sexpr(self): return 'no'

Value.TRUE = W_True()
Value.FALSE = W_False()

grammar.add(Bool, [Word.word("yes")], Literal(Value.TRUE))
grammar.add(Bool, [Word.word("no")], Literal(Value.FALSE))


# Null
# TODO ditch in favour of Options

class W_Null(Value):
    def __init__(self): pass
    def __repr__(self): return 'Value.NULL'
    def sexpr(self): return 'null'
Value.NULL = W_Null()

grammar.add(Bool, [Word.word("null")], Literal(Value.NULL))


# Decimal

#grammar.add(Int, [Word.DIGITS, Word.word("."), Word.DIGITS], ParseDecimal)
# TODO W_Decimal



# Text

Text = Type.get('Text')

# TODO W_Text (using ropes!)

add_type(Int)
add_type(Text)
add_type(Bool)



# Bytecodes

IF = Function("if")
from .ops import *

class ByteCode(Macro):
    def __init__(self, opcode, arg_indexes):
        self.opcode = opcode
        self.arg_indexes = arg_indexes

    def build(self, values, type_):
        args = [(None if index == -1 else values[index]) for index in self.arg_indexes]
        return Instruction(type_, self.opcode, *args)

class Instruction(Tree):
    def __init__(self, type_, opcode, a=None, b=None, c=None):
        self.type = type_
        self.opcode = opcode
        if opcode < HAVE_OUTPUT:
            self.bx = b
            self.c = a
        else:
            self.a = a
            self.b = b
            self.c = c

    def __repr__(self):
        return "<Instruction{}>".format(self.sexpr())

    def sexpr(self):
        if self.opcode < HAVE_OUTPUT:
            args = [self.bx, self.c]
        else:
            args = [self.a, self.b, self.c]
        return "(" + Op.str(self.opcode) + " " + " ".join([("None" if a is None else a.sexpr()) for a in args]) + ")"

    def emit(self, block, env):
        if self.opcode < HAVE_OUTPUT:
            bx = block.compile_node(self.bx, env)
            c = block.compile_node(self.c, env)
            block.emit(self.opcode, bx, c)
            return -1
        else:
            if self.a is None:
                a = block._tmp()
            else:
                a = block.compile_node(self.a, env)
            b = block.compile_node(self.b, env)
            c = block.compile_node(self.c, env)
            block.emit(self.opcode, a, b, c)
            return a

grammar.add(Line, ws([Word.word("NOP")]), ByteCode(Op.NOP, []))

#Label = Type.get('Label')
#grammar.add(Line, ws([Word.word("label"), Word.WORD]), Label)
#grammar.add(Line, ws([Word.word("JUMP"), Label]), Jump(Op.JUMP))
#grammar.add(Line, ws([Word.word("JUMP"), Bool, Label]), Jump(Op.JUMP_IF))
#grammar.add(Line, ws([Word.word("JUMP"), Bool, Label]), Jump(Op.JUMP_UNLESS))

# LOAD_CONSTANT ?

grammar.add(Line, ws([Word.word("ARG"), Type.ANY]), ByteCode(Op.ARG, [-1, 2, -1]))
grammar.add(Generic.ALPHA, ws([Word.word("CALL"), Type.FUNC]), ByteCode(Op.CALL, [-1, 2, -1]))

grammar.add(Int, ws([Word.word("INT_ADD"), Int, Int]), ByteCode(Op.INT_ADD, [-1, 2, 4]))
grammar.add(Int, ws([Word.word("INT_SUB"), Int, Int]), ByteCode(Op.INT_SUB, [-1, 2, 4]))
grammar.add(Bool, ws([Word.word("INT_LT"), Int, Int]), ByteCode(Op.INT_LT, [-1, 2, 4]))


#grammar.add(ALPHA, [ALPHA, Word.word("if"), Bool, Word.word("else"), ALPHA], CallMacro(IF, [4, 0, 8]))
# TODO: don't seem to support left-recursive generics.
grammar.add(ALPHA, ws([Word.word("if"), Bool, Word.word("then"), ALPHA, Word.word("else"), ALPHA]), CallMacro(IF, [2, 6, 10]))

# TODO consider binding user functions with lower precedence...



from .compile import Block, Runtime

# TODO

def parse(source, debug=False):
    tree = grammar_parse(source, grammar, debug)
    assert isinstance(tree, Tree)
    if isinstance(tree, Error):
        return tree.message
    return tree.sexpr()


def parse_and_run(source, debug=False):
    tree = grammar_parse(source, grammar, debug)
    assert isinstance(tree, Tree)
    if isinstance(tree, Error):
        return tree.message

    print tree.sexpr()
    print

    bytecode = Block('program')
    env = bytecode.compile(tree)

    r = Runtime()
    r.run(bytecode, env)

    return ""

