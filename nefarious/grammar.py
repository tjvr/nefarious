
from .types import *
from .values import *
from .lex import Word, Lexer

from .tree import *
from .builtins import Builtin

def Function(name):
    return Name(name)



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

    # TODO fix the above erroneous description

    def build(self, children, type_):
        raise NotImplementedError

    def enter(self, children, type_):
        grammar.save()

    def exit(self, children, type_):
        grammar.restore()

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
        return WordNode(Word.NULL_WS)
# whitespace is always optional, but only permitted if it appears in the defition.
# eg. "Int <> Int" would not allow a space between < and >.
grammar.add(Word.WS, [], Null)


# Internal whitespace helpers

# NLS -> WS* NL (WS | NL)*
Internal.NLS = Internal.get("NLS")
grammar.add(Internal.NLS, [Word.NL], Null)
grammar.add(Internal.NLS, [Word.WS, Internal.NLS], Null)
grammar.add(Internal.NLS, [Internal.NLS, Word.WS], Null)
grammar.add(Internal.NLS, [Internal.NLS, Word.NL], Null)

# SEP -> (WS | NL)*
Internal.SEP = Internal.get("SEP")
grammar.add(Internal.SEP, [], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.WS], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.NL], Null)



# List -- After all, this is "Nefarious Scheme"

@singleton
class EmptyList(Macro):
    def build(self, values, type_):
        return ListLiteral([], type_)
@singleton
class StartList(Macro):
    def build(self, values, type_):
        return ListLiteral([values[0]], type_)
@singleton
class PairList(Macro):
    def build(self, values, type_):
        return ListLiteral([values[0], values[-1]], type_)
@singleton
class ContinueList(Macro):
    def build(self, values, type_):
        list_ = values[0]
        assert isinstance(list_, ListLiteral), type_
        items = list(list_.items)
        items.append(values[-1])
        return ListLiteral(items, type_)


# Generic lists

ALPHA = Generic.ALPHA

@singleton
class EmptyListMacro(Macro):
    def build(self, values, type_):
        return ListLiteral([], type_)
grammar.add(List.get(ALPHA), [
    Word.word("["), Internal.SEP, Word.word("]"),
], EmptyListMacro)

@singleton
class ListMacro(Macro):
    def build(self, values, type_):
        # TODO some kind of type unification on items?
        list_ = values[2]
        assert isinstance(list_, ListLiteral)
        return ListLiteral(list_.items, type_) # TODO redundant!
grammar.add(List.get(ALPHA), [
    Word.word("["), Internal.SEP, Repeat.get(ALPHA), Internal.SEP, Word.word("]"),
], ListMacro)


# Repeat
grammar.add(Repeat.get(ALPHA), [ALPHA], StartList)
grammar.add(Repeat.get(ALPHA), ws([Repeat.get(ALPHA), ALPHA]), ContinueList)


# Parentheses

@singleton
class Parens(Macro):
    def build(self, values, type_):
        child = values[2]
        return child
grammar.add(ALPHA, ws([Word.word("("), ALPHA, Word.word(")")]), Parens)




# Lines

Line = Type.get('Line')
grammar.add(Line, [Type.ANY], Identity)

grammar.add(Seq.get(Line), [], EmptyList)
grammar.add(Seq.get(Line), [Line], StartList)
grammar.add(Seq.get(Line), [Seq.get(Line), Internal.NLS, Line], ContinueList)


# TODO allow newlines inside parens?



# Blocks
@singleton
class BlockMacro(Macro):
    def build(self, values, type_):
        children = values[2]
        if isinstance(children, ListLiteral):
            return Block(children.items)
        else:
            return Block([children])
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
        list_ = values[1]
        assert isinstance(list_, ListLiteral)
        return Block(list_.items)
grammar.add(Type.PROGRAM, [Internal.SEP, Seq.get(Line), Internal.SEP], Program)


# Identifiers

Iden = Internal.get('Iden')

grammar.add(Iden, [Word.WORD], Identity)
grammar.add(Iden, [Word.PUNC], Identity)
grammar.add(Iden, [Word.WS_NOT_NULL], Identity)
# TODO Word.DIGITS ?


# Definitions

Spec = Internal.get('Spec')

class ArgSpec(Node):
    def __init__(self, type_, word):
        assert isinstance(word, WordNode)
        assert isinstance(type_, Literal)
        w_type = type_.value
        assert isinstance(w_type, W_Type)
        self.word = word.word
        self.type = w_type.prim
@singleton
class ArgSpecMacro(Macro):
    def build(self, values, type_):
        type_, _, name = values
        return ArgSpec(type_, name)
grammar.add(Spec, [Type.TYPE, Word.word(":"), Word.WORD], ArgSpecMacro)

grammar.add(Spec, [Iden], Identity)

grammar.add(Seq.get(Spec), [Spec], StartList)
grammar.add(Seq.get(Spec), [Seq.get(Spec), Spec], ContinueList)


@singleton
class DefineMacro(Macro):
    current_definitions = []
    current_definition_args = []

    def _is_arg(self, word):
        return isinstance(word, ArgSpec)

    def _get_spec(self, values):
        spec = values[2]
        assert isinstance(spec, ListLiteral)
        symbols = list(spec.items)
        return symbols

    def _arg_type(self, s):
        if s.type == Type.get('Block'):
            return Type.FUNC
        return s.type

    def enter(self, values, type_):
        grammar.save()
        spec = self._get_spec(values)

        # Build name
        debug_name = ""
        for s in spec:
            if self._is_arg(s):
                assert isinstance(s.type, Type)
                debug_name += s.type._str()
            else:
                assert isinstance(s, WordNode)
                debug_name += s.word.value
        func = Function(debug_name)
        DefineMacro.current_definitions.append(func)

        # Define arguments
        args = []
        for s in spec:
            if isinstance(s, ArgSpec):
                arg = Name.from_word(s.word)
                type_ = self._arg_type(s)
                grammar.add(type_, [s.word], LoadMacro(arg, type_))
                args.append(arg)
        DefineMacro.current_definition_args.append(args)

        # Add internal (recursive) rule
        symbols, macro = self._macro(spec, func)
        grammar.add(ALPHA, symbols, macro)

    def exit(self, values, type_):
        grammar.restore()
        spec = self._get_spec(values)
        func = DefineMacro.current_definitions[-1]

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
        assert type_ is not None, body
        # TODO check unification with `func` calls in body

        # Define rule
        symbols, macro = self._macro(spec, func)
        if values[0].word is Word.word('defprim'):
            node, = body.nodes
            assert isinstance(node, Builtin)
            arg_indexes = []
            arg_names = DefineMacro.current_definition_args[-1]
            for index, arg in enumerate(node._args()):
                assert isinstance(arg, Load)
                arg_indexes.append(arg_names.index(arg.name))
            arg_arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
            macro = BuiltinMacro(node.__class__, [arg_arg_indexes[i] for i in arg_indexes])
        grammar.add(type_, symbols, macro)

    def _macro(self, spec, func):
        symbols = [(s.type if self._is_arg(s) else s.word) for s in spec]
        arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
        return symbols, CallMacro(func, arg_indexes)

    def build(self, values, type_):
        name = DefineMacro.current_definitions.pop()
        arg_names = DefineMacro.current_definition_args.pop()
        body = values[4]

        #return Let(name, Lambda(arg_names, body))
        return Define(name, Func(arg_names, body))


class CallMacro(Macro):
    def __init__(self, call, arg_indexes):
        assert isinstance(call, Name)
        self.call = call
        self.arg_indexes = arg_indexes

    def build(self, values, type_):
        args = [values[i] for i in self.arg_indexes]

        # Block -> Func
        args = [(Lambda(Func([], arg)) if isinstance(arg, Block) else arg) for arg in args]

        # TODO Uneval -> Func

        return Call(Load(self.call, Type.FUNC), args, type_)


grammar.add(Line, ws_not_null([Word.word("define"), Seq.get(Spec), Type.BLOCK,]), DefineMacro)
grammar.add(Line, ws_not_null([Word.word("defprim"), Seq.get(Spec), Type.BLOCK,]), DefineMacro)



# Lambda

Arg = Internal.get('Arg')

grammar.add(Arg, [Type.TYPE, Word.word(":"), Word.WORD], ArgSpecMacro)

grammar.add(Seq.get(Arg), [], EmptyList)
grammar.add(Seq.get(Arg), ws([Seq.get(Arg), Arg]), ContinueList)

@singleton
class LambdaMacro(Macro):
    current_definition_args = []

    def enter(self, values, type_):
        list_ = values[2]
        assert isinstance(list_, W_List)
        spec = list_.items

        grammar.save()

        # Define arguments
        args = []
        for s in spec:
            assert isinstance(s, ArgSpec)
            arg = Name.from_word(s.word)
            if DefineMacro._arg_type(s) != s.type:
                raise SyntaxError("lambda can't have Block or Uneval arguments")
            grammar.add(s.type, [s.word], LoadMacro(arg, s.type))
            args.append(arg)
        LambdaMacro.current_definition_args.append(args)

    def exit(self, values, type_):
        grammar.restore()
        # TODO type check etc

    def build(self, values, type_):
        arg_names = LambdaMacro.current_definition_args.pop()
        body = values[4]
        assert isinstance(body, Block)
        return Lambda(Func(arg_names, body))

grammar.add(Type.FUNC, ws([
    Word.word("fun"), Seq.get(Arg), Type.BLOCK,
]), LambdaMacro)



# Return

@singleton
class ReturnMacro(Macro):
    def build(self, values, type_):
        child = values[2]
        return Return(child)

#grammar.add(Line, [Word.word("return")], ReturnMacro)

grammar.add(Line, ws_not_null([
    Word.word("return"), Type.ANY,
]), ReturnMacro)

#grammar.add(Line, [
#    Word.word("RETURN"), Word.WS, Type.TYPE, Word.word(":"), Type.ANY,
#], ByteCode(Op.RETURN))



# Let

class LoadMacro(Macro):
    def __init__(self, name, type_):
        assert isinstance(name, Name)
        self.name = name
        self.type = type_
    def build(self, values, type_):
        assert self.type == type_
        return Load(self.name, self.type)

@singleton
class LetMacro(Macro):
    def build(self, values, type_):
        value = values[6]

        identifier = values[2].items
        for v in identifier:
            assert isinstance(v, WordNode)
        identifier = [v.word for v in identifier]
        name = ""
        for iden in identifier:
            name += iden.value
        ref = Name(name) # TODO Symbol?

        type_ = value.type
        if type_ is None:
            type_ = Generic.ALPHA # TODO this doesn't work

        grammar.add(type_, identifier, LoadMacro(ref, type_))
        return Let(ref, value)

grammar.add(Seq.get(Iden), [Iden], StartList)
grammar.add(Seq.get(Iden), [Seq.get(Iden), Iden], ContinueList)

grammar.add(Line, ws_not_null([
    Word.word("let"), Seq.get(Iden), Word.word("="), Type.ANY
]), LetMacro)


# Var

Var = Internal.get("Var")

@singleton
class Declare(Macro):
    def build(self, values, type_):
        list_ = values[2]
        assert isinstance(list_, ListLiteral)
        identifier = list_.items
        assert isinstance(identifier, list)
        name = ""
        symbols = []
        for iden in identifier:
            assert isinstance(iden, WordNode)
            symbols.append(iden.word)
            name += iden.word.value

        ref = Name(name)
        grammar.add(Var, symbols, LoadMacro(ref, Var))

        if len(values) > 3:
            value = values[7]
            return StoreCell(NewCell(ref), value)
        else:
            return NewCell(ref)
grammar.add(Line, [
    Word.word("var"), Word.WS_NOT_NULL, Seq.get(Iden)
], Declare)
grammar.add(Line, [
    Word.word("var"), Word.WS_NOT_NULL, Seq.get(Iden), Word.WS_NOT_NULL, Word.word(":"), Word.word("="), Word.WS_NOT_NULL, Type.ANY
], Declare)

@singleton
class LoadCellMacro(Macro):
    def build(self, values, type_):
        load = values[0]
        assert isinstance(load, Load) # TODO iffy
        return LoadCell(load, type_)
grammar.add(Generic.ALPHA, [Var], LoadCellMacro)

@singleton
class StoreCellMacro(Macro):
    def build(self, values, type_):
        load = values[0]
        assert isinstance(load, Load) # TODO iffy
        return StoreCell(load, values[5])
grammar.add(Line, [
    Var, Word.WS_NOT_NULL, Word.word(":"), Word.word("="), Word.WS_NOT_NULL, Type.ANY
], StoreCellMacro)


# Dynamic calls.

@singleton
class DynamicCallMacro(Macro):
    def build(self, values, type_):
        func = values[2]
        if len(values) > 3:
            arg = values[6]
            return Call(func, [arg], type_)
        else:
            return Call(func, [], type_)

grammar.add(Generic.ALPHA, ws_not_null([
    Word.word("call"), Type.FUNC
]), DynamicCallMacro)
grammar.add(Generic.ALPHA, ws_not_null([
    Word.word("call"), Type.FUNC, Word.word("with"), Type.ANY
]), DynamicCallMacro)


# @singleton
# class ApplyMacro(Macro):
#     def build(self, values, type_):
#         return Apply(values[2], values[6], type_)
# 
# grammar.add(Generic.ALPHA, ws_not_null([
#     Word.word("apply"), Type.FUNC, Word.word("to"), List.get(Type.ANY)
# ]), ApplyMacro)

# TODO better syntax: call with Record


# Records

Pair = Internal.get('Pair')
class KVPair(Node):
    def __init__(self, key, value):
        assert isinstance(key, Symbol)
        self.key = key
        self.value = value
@singleton
class PairMacro(Macro):
    def build(self, values, type_):
        _, key, _w, value = values
        assert isinstance(key, WordNode)
        key = key.word
        return KVPair(Symbol.get(key.value), value)
grammar.add(Pair, [Word.word(":"), Word.WORD, Word.WS_NOT_NULL, Type.ANY], PairMacro)

grammar.add(Seq.get(Pair), [], EmptyList)
grammar.add(Seq.get(Pair), [Pair], StartList)
grammar.add(Seq.get(Pair), [Seq.get(Pair), Internal.SEP, Pair], ContinueList)

Record = Type.get('Record')
@singleton
class RecordMacro(Macro):
    def build(self, values, type_):
        pairs = values[2]
        assert isinstance(pairs, ListLiteral)
        keys = []
        values = []
        for p in pairs.items:
            assert isinstance(p, KVPair)
            keys.append(p.key)
            values.append(p.value)
        return RecordLiteral(keys, values, type_)
grammar.add(Type.get('Record'), [Word.word("["), Internal.SEP, Seq.get(Pair), Internal.SEP, Word.word("]")], RecordMacro)

@singleton
class AttrMacro(Macro):
    def build(self, values, type_):
        record, _, word = values
        assert isinstance(word, WordNode)
        symbol = Symbol.get(word.word.value)
        return GetAttr(symbol, record)
grammar.add(Generic.ALPHA, [Type.get('Record'), Word.word("."), Word.WORD], AttrMacro)

@singleton

class SetAttrMacro(Macro):
    def build(self, values, type_):
        record = values[0]
        word = values[2]
        child = values[-1]
        assert isinstance(word, WordNode)
        symbol = Symbol.get(word.word.value)
        return SetAttr(symbol, record, child)
grammar.add(Line, [
    Type.get('Record'), Word.word("."), Word.WORD, Word.WS, Word.word(":"), Word.word("="), Word.WS, Type.ANY,
], SetAttrMacro)


# Types

class LiteralMacro(Macro):
    def __init__(self, value):
        assert isinstance(value, Value)
        self.value = value
    def build(self, values, type_):
        return Literal(self.value, type_)

def add_type(type_):
    name = type_._str()
    assert len(name.split(" ")) == 1
    grammar.add(Type.TYPE, [Word.word(name)], LiteralMacro(W_Type(type_)))

@singleton
class ListTypeMacro(Macro):
    def build(self, values, type_):
        child_type = values[4]
        assert isinstance(child_type, Literal)
        child_type = child_type.value
        assert isinstance(child_type, W_Type)
        return Literal(W_Type(List.get(child_type.prim)), type_)
grammar.add(Type.TYPE, ws([Word.word("("), Word.word("List"), Type.TYPE, Word.word(")")]), ListTypeMacro)

Int = Type.get('Int')
Float = Type.get('Float')
Text = Type.get('Text')
Bool = Type.get('Bool')

grammar.add(Type.TYPE, [Word.word("Block")], LiteralMacro(W_Type(Type.get('Block'))))
grammar.add(Type.TYPE, [Word.word("Func")], LiteralMacro(W_Type(Type.FUNC)))
add_type(Var)

add_type(Int)
add_type(Float)
add_type(Text)
add_type(Bool)
add_type(Type.ANY)
add_type(Record)

#Digits = Type.get('Digits')
#grammar.add(Digits, [Word.word("Digits")], Identity)
#add_type(Digits)


# Built-in builtins
# TODO move to preamble

@singleton
class ParseInt(Macro):
    def build(self, values, type_):
        digits, = values
        assert isinstance(digits, WordNode)
        return Literal(W_Int.fromstr(digits.word.value), type_)
grammar.add(Int, [Word.DIGITS], ParseInt)

@singleton
class ParseFloat(Macro):
    def build(self, values, type_):
        string = ""
        for word in values:
            assert isinstance(word, WordNode)
            string += word.word.value
        return Literal(W_Float.fromstr(string), type_)
grammar.add(Float, [Word.DIGITS, Word.word("."), Word.DIGITS], ParseFloat)
grammar.add(Float, [Word.DIGITS, Word.word("."), Word.DIGITS, Word.word("e"), Word.word("+"), Word.DIGITS], ParseFloat)
grammar.add(Float, [Word.DIGITS, Word.word("."), Word.DIGITS, Word.word("e"), Word.word("-"), Word.DIGITS], ParseFloat)

@singleton
class ParseText(Macro):
    def build(self, values, type_):
        word = values[0]
        assert isinstance(word, WordNode)
        word = word.word
        return Literal(W_Text.fromstr(word.value), type_)
grammar.add(Text, [Word.TEXT], ParseText)

grammar.add(Bool, [Word.word("yes")], LiteralMacro(Value.TRUE))
grammar.add(Bool, [Word.word("no")], LiteralMacro(Value.FALSE))
#grammar.add(Null, [Word.word("nil")], Literal(Value.NULL))



# Built in function nodes

class BuiltinMacro(Macro):
    def __init__(self, cls, arg_indexes):
        #assert issubclass(cls, Builtin)
        self.cls = cls
        self.arg_indexes = arg_indexes

    def build(self, values, type_):
        args = [values[i] for i in self.arg_indexes]
        return self.cls(args, type_)

def add_builtin(cls):
    name = cls.__name__
    out = cls.type
    assert isinstance(out, Type), out
    args = cls.arg_types
    symbols = ws([Word.word(name)] + args)
    arg_indexes = [i for i in range(len(symbols)) if isinstance(symbols[i], Type)]
    assert len(arg_indexes) == len(args)
    grammar.add(out, symbols, BuiltinMacro(cls, arg_indexes))

import builtins
for name in dir(builtins):
    cls = getattr(builtins, name)
    if name.replace("_", "").isupper():
        if cls is not Builtin and issubclass(cls, Builtin):
            add_builtin(cls)



# TODO

def parse(source, debug=False):
    tree = grammar_parse(source, grammar, debug)
    assert isinstance(tree, Node)
    if isinstance(tree, Error):
        return tree.message
    return tree.sexpr()


def parse_and_run(source, debug=False):
    tree = grammar_parse(source, grammar, debug)
    assert isinstance(tree, Node)
    if isinstance(tree, Error):
        return tree.message
    assert isinstance(tree, Block)

    print(tree.sexpr())
    #print(repr(tree))
    print

    stack = [Shape.get([])]
    tree.compile(stack)
    shape = stack.pop()

    main = Func([], None)
    root = Frame(None, shape)

    retval = tree.evaluate(root)
    if retval is None:
        print "=> None"
        return ""

    print
    print("=> " + retval.sexpr())
    print(retval.type._str())
    #print(retval) # Useless on RPython!

    return ""

