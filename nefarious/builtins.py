
from .lex import Word
#from .grammar import Name, grammar, ws, CallMacro
from .grammar import *
from .values import *


class W_Builtin(Value):
    def __init__(self, impl):
        self.impl = impl

    def call(self, args, scope_or_grammar):
        raise NotImplementedError

    @staticmethod
    def cls(size):
        assert size <= 3
        return [Builtin0, Builtin1, Builtin2, Builtin3][size]

class Builtin0(W_Builtin):
    def call(self, args, scope):
        assert len(args) == 0
        return self.impl(scope)

class Builtin1(W_Builtin):
    def call(self, args, scope):
        assert len(args) == 1
        return self.impl(args[0], scope)

class Builtin2(W_Builtin):
    def call(self, args, scope):
        assert len(args) == 2
        return self.impl(args[0], args[1], scope)

class Builtin3(W_Builtin):
    def call(self, args, scope):
        assert len(args) == 3
        return self.impl(args[0], args[1], args[2], scope)

#------------------------------------------------------------------------------

from .runtime import Scope, eval_
builtins = Scope()

# TODO uneval

Uneval = Internal.get('Uneval')
@singleton
class QuoteMacro(Macro):
    def build(self, values, type_):
        assert len(values) == 1
        return Quote(values[0], type_)
grammar.add(Uneval, [ALPHA], QuoteMacro)

class CallMacro(Macro):
    def __init__(self, call, arg_indexes):
        assert isinstance(call, Name)
        self.call = call
        self.arg_indexes = arg_indexes

    def build(self, values, type_):
        args = [values[i] for i in self.arg_indexes]
        return Call(self.call, type_, args)

def defrule(target, symbols):
    indexes = [i for i in range(len(symbols)) if not isinstance(symbols[i], Word)]
    def wrap(impl):
        name = Name(Type.FUNC, impl.__name__)
        cls = W_Builtin.cls(len(indexes))
        builtins.set(name, cls(impl))
        grammar.add(target, symbols, CallMacro(name, indexes))
        return impl
    return wrap 

class MacroMacro(Macro):
    def __init__(self, builtin, arg_indexes):
        self.builtin = builtin
        self.arg_indexes = arg_indexes

    def build(self, values, type_):
        args = [values[i] for i in self.arg_indexes]
        return self.builtin.call(args, None)

def macro(target, symbols, indexes=None):
    if indexes is None:
        indexes = [i for i in range(len(symbols)) if not isinstance(symbols[i], Word)]
    def wrap(impl):
        assert len(indexes) <= 5
        cls = W_Builtin.cls(len(indexes))
        builtin = cls(impl)
        grammar.add(target, symbols, MacroMacro(builtin, indexes))
        return impl
    return wrap 

#------------------------------------------------------------------------------

Bool = Type.get("Bool")
@macro(Bool, [Word.word("yes")])
def yes(scope):
    return Value.TRUE

@macro(Bool, [Word.word("no")])
def no(scope):
    return Value.FALSE

@defrule(Bool, ws([Word.word("not"), Bool]))
def not_(value, scope):
    if value == Value.TRUE:
        return Value.FALSE
    elif value == Value.FALSE:
        return Value.TRUE
    else:
        assert False, value


Int = Type.get("Int")

@macro(Int, [Word.DIGITS], [0])
def parse_int(digits, scope):
    assert isinstance(digits, Word)
    return W_Int(int(digits.value))
 
@defrule(Int, ws([Int, Word.word("+"), Int]))
def int_add(a, b, scope):
    assert isinstance(a, W_Int)
    assert isinstance(b, W_Int)
    return W_Int(a.value + b.value)

@defrule(Int, ws([Int, Word.word("-"), Int]))
def int_sub(a, b, scope):
    assert isinstance(a, W_Int)
    assert isinstance(b, W_Int)
    return W_Int(a.value - b.value)

@defrule(Bool, ws([Int, Word.word("<"), Int]))
def int_lt(a, b, scope):
    assert isinstance(a, W_Int)
    assert isinstance(b, W_Int)
    return W_Bool.get(a.value < b.value)



@defrule(Line, ws([Word.word("print"), Type.ANY]))
def print_(value, scope):
    print(value.sexpr())



#@defrule(ALPHA, [ALPHA, Word.word("if"), Bool, Word.word("else"), ALPHA]) # TODO: support left-recursive generics
@defrule(ALPHA, ws([Word.word("if"), Bool, Word.word("then"), Uneval, Word.word("else"), Uneval]))
def if_then_else(test, tv, fv, scope):
    if test == Value.TRUE:
        return eval_(tv, scope)
    elif test == Value.FALSE:
        return eval_(fv, scope)
    else:
        assert False



#@define("List", "map Block:func over List:seq")
#def map(block, seq):
#    return ...


