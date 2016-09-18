
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
        return "(" + self.type.sexpr() + " " + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"

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

@singleton
class StartList(Macro):
    def build(self, values, type_):
        return Call(LIST, type_, [values[0]])

@singleton
class PairList(Macro):
    def build(self, values, type_):
        return Call(LIST, type_, [values[0], values[-1]])

@singleton
class ContinueList(Macro):
    def build(self, values, type_):
        list_ = values[0]
        assert isinstance(list_, Call) and list_.func is LIST
        list_.args.append(values[-1])
        return list_


# Define -- the most important function (!)
DEFINE = Function('define')
Spec = Type.get('Spec')

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

grammar.add(Type.ANY, [
    Word.word('define'), Word.WS, Seq.get(Type.get('Spec')), Word.WS, Word.word("{"),
], Define)

WORD = Function('word')
@singleton
class WordMacro(Macro):
    def build(self, values, type_):
        return Call(WORD, type_, values)
grammar.add(Spec, [Word.WORD], WordMacro)

grammar.add(Seq.get(Spec), [Spec], StartList)
grammar.add(Seq.get(Spec), [Seq.get(Spec), Word.WS, Spec], ContinueList)


# Lists

alpha = Generic.get(1)
grammar.add(List.get(alpha), [alpha, Word.WS, Word.word(","), Word.WS, alpha], PairList)
grammar.add(List.get(alpha), [List.get(alpha), Word.WS, Word.word(","), Word.WS, alpha], ContinueList)


# Generic parentheses!

@singleton
class Parens(Macro):
    def build(self, values, type_):
        child = values[2]
        assert type_ == child.type
        return child
grammar.add(Generic.get(1), [Word.word("("), Word.WS, Generic.get(1), Word.WS, Word.word(")")], Parens)

CHOICE = Function('choice')
@singleton
class Choice(Macro):
    def build(self, values, type_):
        return Call(CHOICE, [values[2], values[6]])
grammar.add(Generic.get(1), [Word.word("choose"), Word.WS, Generic.get(1), Word.WS, Word.word("or"), Word.WS, Generic.get(1)], Choice)

CMP = Function('cmp')
@singleton
class Cmp(Macro):
    def build(self, values, type_):
        return Call(CMP, [values[0], values[4]])
grammar.add(Type.get('Bool'), [Generic.get(1), Word.WS, Word.word("<"), Word.WS, Generic.get(1)], Cmp)



#grammar.add(Type.PROGRAM, [Word.word('hello'), Word.NL], Function('hello'))

Int = Type.get('Int')
Text = Type.get('Text')
Bool = Type.get('Bool')

grammar.add(Type.PROGRAM, [Type.ANY, Word.NL], Identity)


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

#from pprint import pprint
#pprint(grammar.scope.rule_sets)
#print

def parse(source, debug=False):
    return grammar_parse(source, grammar, debug)

