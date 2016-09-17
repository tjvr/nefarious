
from .types import *
from .lex import Word, Lexer

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

    def build(self, children):
        return Call(self, children)

    def call_immediate(self, children):
        assert self.body is not None
        pass # TODO

class Macro(Function):
    def build(self, children):
        return self.call_immediate(children)

    def sexpr(self):
        assert False # macros should never be in the AST!

class Call(Tree):
    def __init__(self, func, args):
        assert isinstance(func, Function)
        self.func = func
        assert isinstance(args, list)
        for arg in args:
            assert isinstance(arg, Tree)
        self.args = args

    def sexpr(self):
        return "(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"



COERCE = Function('coerce')
class CoerceMacro(Macro):
    def __init__(self, type_):
        self.type = type_
    def build(self, values):
        assert len(values) == 1
        return Call(COERCE, [self.type, values[0]])

from .parser import Grammar, Rule, grammar_parse

grammar = Grammar()

def singleton(cls):
    return cls(cls.__name__)

DEFINE = Function('define')
# MACRO = Function('macro') # macro definitions do not get sent to the compiler!

# nullable whitespace derivation -- whitespace is always optional.
# note however that whitespace has to be explicitly allowed, eg. "Int <> Int"
# would not allow a space between < and >.
# ie. whitespace is only permitted if it appears in the definition.

@singleton
class Null(Macro):
    def build(self, values):
        return Word.NULL_WS
grammar.add(Word.WS, [], Null)

# For, um, lists.
# After all, this is "Nefarious Scheme"
LIST = Function('list')

@singleton
class StartList(Macro):
    def build(self, values):
        assert len(values) == 1
        child = values[0]
        return Call(LIST, [child])

@singleton
class ContinueList(Macro):
    def build(self, values):
        list_ = values[0]
        assert isinstance(list_, Call)
        assert list_.func is LIST
        list_.args.append(values[-1])
        return list_

# For, um, subtypes and stuff.
@singleton
class Identity(Macro):
    def build(self, values):
        assert len(values) == 1
        return values[0]


def add_list(target, cont):
    symbols = [target] + cont
    grammar.add(target, symbols, ContinueList)
    item = cont[-1]
    grammar.add(target, [item], StartList)

#add_list(Type.get('SpecList'), [Type.get('Spec')])
#add_list(Type.get('Block'), [Type.get('Line')])

# We want to--
# - allow for scoping the inside of blocks.
#   so eg. an `sql _` statement that accepts a block -- `sql { select * from ... }`
# - allow recursive definitions. `define fib Int:n { return fib ... }`
# - allow generic types. eg. (List 'a) -> (List 'a) "," 'a
#
# when *does* evaluation happen?
# is there a way to let evaluation affect prediction? That seems *somewhat*
# what we want to allow for here...
#
# Aside from generics, it would be fine if evaluation/scoping was hard-bound to
# { }...

# Generics.
# =========
#
# Prediction: ask Grammar for all subtypes of T.
# Always include "Wild".
# Generics expand to any type.   'a -> Wild, Int, Frac, Text ...
#
# Completion: unify right with left.wants.
# Create new (but uniqued!) LR0s.
# right must be a *subtype* of left.wants!
# and target must be a *subtype* of the original wanted_by ~ target.
# Unification can fail!

#grammar.add_type(Generic.ALPHA)
# Don't need to add the Wild type -- grammar.expand() always returns it.

@singleton
class TypeMacro(Macro):
    def build(self, values):
        return Type.get(values[0].value)

# add_type: what should Type.ANY expand to?
grammar.add_type(Type.get('Int'))
grammar.add_type(Type.get('Text'))
grammar.add_type(Type.get('Bool'))
grammar.add_type(List.get(Type.ANY))

class CallMacro(Macro):
    def __init__(self, call, arg_indexes):
        assert isinstance(call, Function) and not isinstance(call, Macro)
        self.call = call
        self.arg_indexes = arg_indexes
    def build(self, values):
        args = [values[i] for i in self.arg_indexes]
        return Call(self.call, args)



alpha = Generic.get(1)
grammar.add(List.get(alpha), [alpha], StartList)
grammar.add(List.get(alpha), [List.get(alpha), Word.WS, Word.word(","), Word.WS, alpha], ContinueList)

# Generic parentheses!

@singleton
class Parens(Macro):
    def build(self, values):
        return values[2]
grammar.add(Generic.get(1), [Word.word("("), Word.WS, Generic.get(1), Word.WS, Word.word(")")], Parens)

CHOICE = Function('choice')
@singleton
class Choice(Macro):
    def build(self, values):
        return Call(CHOICE, [values[2], values[6]])
grammar.add(Generic.get(1), [Word.word("choose"), Word.WS, Generic.get(1), Word.WS, Word.word("or"), Word.WS, Generic.get(1)], Choice)

CMP = Function('cmp')
@singleton
class Cmp(Macro):
    def build(self, values):
        return Call(CMP, [values[0], values[4]])
grammar.add(Type.get('Bool'), [Generic.get(1), Word.WS, Word.word("<"), Word.WS, Generic.get(1)], Cmp)



#grammar.add(Type.PROGRAM, [Word.word('hello'), Word.NL], Function('hello'))

Int = Type.get('Int')
Text = Type.get('Text')
Bool = Type.get('Bool')

grammar.add(Type.PROGRAM, [Type.ANY, Word.NL], Identity)
#grammar.add(Type.ANY, [Int], Identity)
#grammar.add(Type.PROGRAM, [Int, Word.NL], Identity)
#grammar.add(Type.PROGRAM, [Text, Word.NL], Identity)
#grammar.add(Type.PROGRAM, [Bool, Word.NL], Identity)

grammar.add(Int, [Word.word('hello')], Identity)
grammar.add(Text, [Word.word('goodbye')], Identity)
grammar.add(Bool, [Word.word('false')], Identity)

grammar.add(Int, [Int, Word.WS, Word.word("+"), Word.WS, Int], CallMacro(Function('+'), [0, 4]))

grammar.add(Generic.ALPHA, [Word.word('foo')], Identity)

grammar.add(List.get(Int), [Word.word('range'), Word.WS, Int, Word.WS, Word.word('to'), Word.WS, Int], CallMacro(Function('range'), [2, 6]))


#grammar.add_list(List(Generic(0)), [Word.get(","), Generic(0)])

# grammar.add(Type.get('_PreDef'), [
#     Type.get('_PreDef'),
#     Type.get('Block'),
#     Word.get('{'),
# ], PreDef)
#
# grammar.add(Type.get('Line'), [
#     Type.get('_PreDef'),
#     Type.get('Block'),
#     Word.get('}'),
# ], PostDef)

from pprint import pprint
pprint(grammar.scope.rule_sets)
print

def parse(source, debug=False):
    return grammar_parse(source, grammar, debug)

