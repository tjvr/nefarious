
from .types import *
from .values import *
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
        inner = " ".join([a.sexpr() for a in self.args])
        return "(" + self.func.sexpr() + " " + inner + ")"
        #return self.type.sexpr() + ":(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"


class Block(Tree):
    type = Type.BLOCK

    def __init__(self, nodes):
        assert isinstance(nodes, list)
        for node in nodes:
            assert isinstance(node, Tree)
        self.nodes = nodes

    def __repr__(self):
        return "Block({!r})".format(self.nodes)

    def sexpr(self):
        indent = "  "
        inner = "\n".join([a.sexpr() for a in self.nodes])
        inner = indent + ("\n" + indent).join(inner.split("\n"))
        return "{\n" + inner + "\n}"


class Quote(Tree):
    def __init__(self, child, type_):
        assert isinstance(child, Tree)
        self.child = child
        assert isinstance(type_, Type)
        self.type = type_

    def __repr__(self):
        return "Block({!r})".format(self.child)

    def sexpr(self):
        return "(quote " + self.child.sexpr() + ")"


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
    def __init__(self, call, arg_indexes, uneval=None):
        assert isinstance(call, Name)
        self.call = call
        self.arg_indexes = arg_indexes
        self.uneval = uneval

    def build(self, values, type_):
        args = [values[i] for i in self.arg_indexes]
        if self.uneval is not None:
            for index in self.uneval:
                # type_ ?
                pass
                #args[index] = Call(QUOTE, type_, [args[index]])
        return Call(self.call, type_, args)

# TODO CustomMacros
#    return self.call_immediate(children)


grammar = Grammar()

def singleton(cls):
    return cls()

@singleton
class Identity(Macro):
    def build(self, values, type_):
        assert len(values) == 1, "Identity macro fail"
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
@singleton
class BlockMacro(Macro):
    def build(self, values, type_):
        return Block(values[2].args)
grammar.add(Type.BLOCK, [Word.word("{"), Internal.SEP, Seq.get(Line), Internal.SEP, Word.word("}")], BlockMacro)

@singleton
class EmptyBlock(Macro):
    def build(self, values, type_):
        return Block([])
grammar.add(Type.BLOCK, [Word.word("{"), Word.word("}")], EmptyBlock)


# Program
@singleton
class Program(Macro):
    def build(self, values, type_):
        return Block(values[1].args)
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
        symbols, macro = self._macro(spec, func)
        grammar.add(ALPHA, symbols, macro)

    def exit(self, values, type_):
        grammar.restore()
        spec = self._get_spec(values)
        func = Define.current_definitions[-1]

        # Type check
        body = values[-1]
        assert isinstance(body, Block)
        if len(body.nodes) == 0: # empty block
            type_ = Line # ??
        elif len(body.nodes) == 1:
            type_ = body.nodes[0].type
        else:
            # TODO walk AST for `return` statements
            type_ = body.nodes[-1].type
        # TODO check unification with `func` calls in body

        # Define rule
        symbols, macro = self._macro(spec, func)
        grammar.add(type_, symbols, macro)

    def _macro(self, spec, func):
        symbols = [(s.args[0] if self._is_arg(s) else s) for s in spec]
        arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
        #uneval = [arg_indexes.index(index) for index in arg_indexes
        #          if symbols[index] == Var]
        return symbols, CallMacro(func, arg_indexes, [])

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

Var = Internal.get("Var")
VAR = Function("var")
add_type(Var)

@singleton
class Declare(Macro):
    def build(self, values, type_):
        identifier = values[2].args
        name = ""
        for iden in identifier:
            assert isinstance(iden, Word)
            name += iden.value

        var = Name(Generic.ALPHA, name)

        # fit Var slot
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

GET = Function("get")
grammar.add(Generic.ALPHA, [Var], CallMacro(GET, [0]))


SET = Function("set")

# TODO don't parse `y := 4` as (set (get y) 4)
grammar.add(Line, [
    Var, Word.WS_NOT_NULL, Word.word(":"), Word.word("="), Word.WS_NOT_NULL, Type.ANY
], CallMacro(SET, [0, 5]))

# TODO pass var cells by reference!


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


# Null

# Text

Int = Type.get('Int')
Text = Type.get('Text')
Bool = Type.get('Bool')

add_type(Int)
add_type(Text)
add_type(Bool)


from .builtins import builtins
from .runtime import Scope, eval_

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
    assert isinstance(tree, Block)

    print(tree.sexpr())
    print

    scope = Scope(builtins)
    retval = eval_(tree, scope)

    print
    print("=> " + retval.sexpr())
    print(retval)

    return ""

