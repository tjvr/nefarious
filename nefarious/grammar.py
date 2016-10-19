
from .types import *
from .values import *
from .lex import Word, Lexer

from .tree import *

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
        return Call(Load(self.call, Type.FUNC), args, type_)

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

@singleton
class EmptyList(Macro):
    def build(self, values, type_):
        return W_List([])
@singleton
class StartList(Macro):
    def build(self, values, type_):
        return W_List([values[0]])
@singleton
class PairList(Macro):
    def build(self, values, type_):
        return W_List([values[0], values[-1]])
@singleton
class ContinueList(Macro):
    def build(self, values, type_):
        list_ = values[0]
        assert isinstance(list_, W_List)
        items = list(list_.items)
        items.append(values[-1])
        return W_List(items)



# Generic lists
# TODO require square brackets?

ALPHA = Generic.ALPHA

@singleton
class PairListMacro(Macro):
    def build(self, values, type_):
        return Literal(W_List([values[0], values[-1]]), type_)
grammar.add(List.get(ALPHA), ws([
    ALPHA, Word.word(","), ALPHA,
]), PairListMacro)

@singleton
class ContinueListMacro(Macro):
    def build(self, values, type_):
        assert isinstance(values[0], Literal)
        list_ = values[0].value
        assert isinstance(list_, W_List)
        items = list(list_.items)
        items.append(values[-1])
        return Literal(W_List(items), type_)
grammar.add(List.get(ALPHA), ws([
    List.get(ALPHA), Word.word(","), ALPHA,
]), ContinueListMacro)

@singleton
class EmptyListMacro(Macro):
    def build(self, values, type_):
        return Literal(W_List([]), type_)
grammar.add(List.get(ALPHA), ws([
    Word.word("["), Word.word("]"),
]), EmptyListMacro)

@singleton
class OneListMacro(Macro):
    def build(self, values, type_):
        return Literal(W_List([values[2]]), type_)
grammar.add(List.get(ALPHA), ws([
    Word.word("["), ALPHA, Word.word("]"),
]), OneListMacro)
grammar.add(List.get(ALPHA), ws([
    Word.word("["), ALPHA, Word.word(","), Word.word("]"),
]), OneListMacro)

@singleton
class EncloseListMacro(Macro):
    def build(self, values, type_):
        return values[2]
grammar.add(List.get(ALPHA), ws([
    Word.word("["), List.get(ALPHA), Word.word("]"),
]), EncloseListMacro)
grammar.add(List.get(ALPHA), ws([
    Word.word("["), List.get(ALPHA), Word.word(","), Word.word("]"),
]), EncloseListMacro)



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

Internal.SEP = Internal.get("SEP")
grammar.add(Internal.SEP, [], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.WS], Null)
grammar.add(Internal.SEP, [Internal.SEP, Word.NL], Null)

grammar.add(Seq.get(Line), [], EmptyList)
grammar.add(Seq.get(Line), [Line], StartList)
grammar.add(Seq.get(Line), [Seq.get(Line), Internal.SEP, Line], ContinueList)


# Blocks
@singleton
class BlockMacro(Macro):
    def build(self, values, type_):
        children = values[2]
        if isinstance(children, W_List):
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
        assert isinstance(list_, W_List)
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

class ArgSpec(Tree):
    def __init__(self, type_, name):
        assert isinstance(name, Word)
        assert isinstance(type_, Type)
        self.name = name
        self.type = type_

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
        assert isinstance(spec, W_List)
        symbols = list(spec.items)
        return symbols

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
                assert isinstance(s, Word)
                debug_name += s.value
        func = Function(debug_name)
        DefineMacro.current_definitions.append(func)

        # Define arguments
        args = []
        for s in spec:
            if self._is_arg(s):
                assert isinstance(s, ArgSpec)
                assert isinstance(s.name, Word)
                arg = Name(s.name.value)
                grammar.add(s.type, [s.name], LoadMacro(arg, s.type))
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
        grammar.add(type_, symbols, macro)

    def _macro(self, spec, func):
        symbols = [(s.type if self._is_arg(s) else s) for s in spec]
        arg_indexes = [index for index, s in enumerate(spec) if self._is_arg(s)]
        return symbols, CallMacro(func, arg_indexes)

    def build(self, values, type_):
        name = DefineMacro.current_definitions.pop()
        arg_names = DefineMacro.current_definition_args.pop()
        body = values[4]

        #return Let(name, Lambda(arg_names, body))
        return Define(name, Func(arg_names, body))

grammar.add(Line, ws_not_null([
    Word.word("define"), Seq.get(Spec), Type.BLOCK,
]), DefineMacro)



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
            arg = Name(s.name.value)
            grammar.add(s.type, [s.name], LoadMacro(arg, s.type))
            args.append(arg)
        LambdaMacro.current_definition_args.append(args)

    def exit(self, values, type_):
        grammar.restore()
        # TODO type check etc

    def build(self, values, type_):
        arg_names = LambdaMacro.current_definition_args.pop()
        body = values[4]
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
        name = ""
        for iden in identifier:
            assert isinstance(iden, Word)
            name += iden.value
        var = Name(name) # TODO Symbol?

        type_ = value.type
        if type_ is None:
            type_ = Generic.ALPHA # TODO this doesn't work

        grammar.add(type_, identifier, LoadMacro(var, type_))
        return Let(var, value)

grammar.add(Seq.get(Iden), [Iden], StartList)
grammar.add(Seq.get(Iden), [Seq.get(Iden), Iden], ContinueList)

grammar.add(Line, ws_not_null([
    Word.word("let"), Seq.get(Iden), Word.word("="), Type.ANY
]), LetMacro)


# Var

# Var = Internal.get("Var")
# VAR = Function("var")
# add_type(Var)
# 
# @singleton
# class Declare(Macro):
#     def build(self, values, type_):
#         identifier = values[2].args
#         name = ""
#         for iden in identifier:
#             assert isinstance(iden, Word)
#             name += iden.value
# 
#         var = Name(name)
# 
#         # TODO var = LoadCell
# 
#         # fit Var slot
#         #grammar.add(Var, identifier, LoadCellMacro(var))
# 
#         if len(values) > 3:
#             value = values[7]
#             return Call(VAR, type_, [var, value])
#         else:
#             return Call(VAR, type_, [var])
# 
# grammar.add(Line, [
#     Word.word("var"), Word.WS_NOT_NULL, Seq.get(Iden)
# ], Declare)
# grammar.add(Line, [
#     Word.word("var"), Word.WS_NOT_NULL, Seq.get(Iden), Word.WS_NOT_NULL, Word.word(":"), Word.word("="), Word.WS_NOT_NULL, Type.ANY
# ], Declare)
# 
# GET = Function("get")
# grammar.add(Generic.ALPHA, [Var], CallMacro(GET, [0]))
# 
# 
# SET = Function("set")
# 
# # TODO don't parse `y := 4` as (set (get y) 4)
# grammar.add(Line, [
#     Var, Word.WS_NOT_NULL, Word.word(":"), Word.word("="), Word.WS_NOT_NULL, Type.ANY
# ], CallMacro(SET, [0, 5]))
# 
# # TODO pass var cells by reference!



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
# TODO better syntax: call with Record
# TODO apply Func: to List:





# Types

# TODO type grammar

class LiteralMacro(Macro):
    def __init__(self, value):
        self.value = value
    def build(self, values, type_):
        return self.value

def add_type(type_):
    name = type_._str()
    assert len(name.split(" ")) == 1
    grammar.add(Type.TYPE, [Word.word(name)], LiteralMacro(type_))

@singleton
class ListTypeMacro(Macro):
    def build(self, values, type_):
        return List.get(values[4])

grammar.add(Type.TYPE, ws([Word.word("("), Word.word("List"), Type.TYPE, Word.word(")")]), ListTypeMacro)

Int = Type.get('Int')
Text = Type.get('Text')
Bool = Type.get('Bool')

add_type(Int)
add_type(Text)
add_type(Bool)
add_type(Type.ANY)



# TODO built-ins...

@singleton
class ParseInt(Macro):
    def build(self, values, type_):
        digits, = values
        assert isinstance(digits, Word)
        return Literal(W_Int(int(digits.value)), type_)
grammar.add(Int, [Word.DIGITS], ParseInt)




main = Func([], None)
builtins = Frame(None, main, [])

builtins.set #...




# Uneval = Internal.get('Uneval')
# @singleton
# class QuoteMacro(Macro):
#     def build(self, values, type_):
#         assert len(values) == 1
#         return Quote(values[0], type_)
# grammar.add(Uneval, [ALPHA], QuoteMacro)
# 
# class CallMacro(Macro):
#     def __init__(self, name, arg_indexes):
#         assert isinstance(name, Name)
#         self.name = name
#         self.arg_indexes = arg_indexes
# 
#     def build(self, values, type_):
#         args = [values[i] for i in self.arg_indexes]
#         func = Load(self.name)
#         return Call(func, args)
# 
# def defrule(target, symbols):
#     indexes = [i for i in range(len(symbols)) if not isinstance(symbols[i], Word)]
#     def wrap(impl):
#         name = Name(impl.__name__)
#         cls = W_Builtin.cls(len(indexes))
#         builtins.set(name, cls(impl))
#         grammar.add(target, symbols, CallMacro(name, indexes))
#         return impl
#     return wrap
# 
# class MacroMacro(Macro):
#     def __init__(self, builtin, arg_indexes):
#         self.builtin = builtin
#         self.arg_indexes = arg_indexes
# 
#     def build(self, values, type_):
#         args = [values[i] for i in self.arg_indexes]
#         return self.builtin.call(args, None)
# 
# def macro(target, symbols, indexes=None):
#     if indexes is None:
#         indexes = [i for i in range(len(symbols)) if not isinstance(symbols[i], Word)]
#     def wrap(impl):
#         assert len(indexes) <= 5
#         cls = W_Builtin.cls(len(indexes))
#         builtin = cls(impl)
#         grammar.add(target, symbols, MacroMacro(builtin, indexes))
#         return impl
#     return wrap



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
    #print(repr(tree))
    print

    retval = tree.evaluate(builtins)
    if retval is None:
        print "=> None"
        return ""

    print
    print("=> " + retval.sexpr())
    #print(retval) # Useless on RPython!

    return ""

