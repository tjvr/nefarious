
import struct

try:
    from rpython.rlib.objectmodel import we_are_translated
except ImportError:
    def we_are_translated(): return False

from .grammar import *
from .builtins import W_Builtin


#------------------------------------------------------------------------------

try:
    from rpython.rlib.jit import JitDriver, purefunction
except ImportError:
    # Dummy class for running under standard CPython
    class JitDriver(object):
        def __init__(self,**kw): pass
        def jit_merge_point(self,**kw): pass
        def can_enter_jit(self,**kw): pass
    def purefunction(f): return f

def jitpolicy(driver):
    from rpython.jit.codewriter.policy import JitPolicy
    return JitPolicy()


# greens: loop constants. identify loop.                eg. code object & instruction pointer
# reds: everything else used in the execution loop.     eg. frame object & execution context
jitdriver = JitDriver(
    greens=['node'], # TODO
    virtualizables=[],
    reds=['scope'], # TODO
    is_recursive=True,
)

def get_location(node):
    return node.sexpr()


#------------------------------------------------------------------------------


class Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.names = {}
        self._cache = {}

    def lookup(self, name):
        assert isinstance(name, Name)
        if name in self.names:
            return self.names[name]
        if self.parent:
            if name in self._cache:
                value = self._cache[name]
            else:
                value = self._cache[name] = self.parent.lookup(name)
            return value
        raise AttributeError("name '" + name.name + "' not defined in scope")

    def set(self, name, value):
        assert isinstance(name, Name)
        assert name not in self.names # name bindings are immutable!
        self.names[name] = value


class Closure(Value):
    def __init__(self, func, scope):
        self.func = func
        self.scope = scope

    def call(self, args):
        func = self.func
        scope = Scope(self.scope)
        assert len(func.arg_names) == len(args)
        for i in range(len(args)):
            name = func.arg_names[i]
            value = args[i]
            scope.set(name, value)
        return eval_(func.block, scope)

class Func(Value):
    def __init__(self, name, args, block):
        self.debug_name = name
        self.arg_names = args
        self.block = block

def eval_(node, scope):

    jitdriver.jit_merge_point(node=node, scope=scope)

    if isinstance(node, Call):
        return eval_call(node.func, node.args, scope)
    elif isinstance(node, Name):
        return scope.lookup(node)
    elif isinstance(node, Block):
        return eval_block(node, scope)
    elif isinstance(node, Closure):
        assert False, node
    elif isinstance(node, Quote):
        return node.child
    elif isinstance(node, Value): # TODO careful! Blocks are Values too
        return node
    else:
        assert False, node.sexpr()

def eval_block(block, scope):
    value = None
    for node in block.nodes:
        value = eval_(node, scope)
    return value

def eval_call(call, args, scope):
    # TODO attach these to outermost scope somehow
    if call == LET:
        name, value = args
        value = eval_(value, scope)
        scope.set(name, value)
        return
    elif call == DEFINE:
        args = list(args)
        body = args.pop()
        name = args.pop(0)
        assert isinstance(body, Block)
        closure = Closure(Func(name.name, args, body), scope)
        scope.set(name, closure)
        return
    else:
        func = eval_(call, scope)
        args = [eval_(arg, scope) for arg in args]
        if isinstance(func, W_Builtin):
            return func.call(args, scope)
        assert isinstance(func, Closure)
        return func.call(args)


