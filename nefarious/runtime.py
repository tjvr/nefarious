
import struct

try:
    from rpython.rlib.objectmodel import we_are_translated
except ImportError:
    def we_are_translated(): return False


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

from .types import *
from .values import *

class Name(Tree):
    """Symbol. Compared by identity, not value, so shadowing works."""
    def __init__(self, type_, name):
        assert isinstance(type_, Type)
        assert isinstance(name, str)
        self.type = type_
        self.name = name # String name really is just a debugging aid
        self._parent = None

    def __repr__(self):
        return "Name({!r}, {!r})".format(self.type, self.name)

    def sexpr(self):
        return self.name.replace(" ", "_")

    def evaluate(self, frame):
        try:
            index = frame.local_names.index(self)
        except IndexError:
            node = NonLocalNode(self)
        else:
            node = LocalNode(index)
        self._parent.replace_child(self, node)
        return node.evaluate(frame)


class LocalNode(Name):
    def __init__(self, index):
        self.index = index

    def evaluate(self, frame):
        return frame.locals[index]

class NonLocalNode(Name):
    def __init__(self, key):
        self.key = key

    def evaluate(self, frame):
        return frame.parent.lookup(self.key)


class Error(Tree):
    def __init__(self, message):
        self.message = message


class CallNode(Tree):
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
        return "<CallNode {!r} {!r}>".format(self.func.name, self.args)

    def sexpr(self):
        inner = " ".join([a.sexpr() for a in self.args])
        return "(" + self.func.sexpr() + " " + inner + ")"
        #return self.type.sexpr() + ":(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"

    def replace_child(self, child, other):
        if child == self.func:
            self.func = other
        for i in range(len(self.args)):
            if self.args[i] == child:
                self.args[i] = other
        other._parent = self

    def evaluate(self, frame):
        node = StaticCallNode(self.func, self.args)
        self._parent.replace_child(self, node)
        return node.evaluate(frame)

class StaticCallNode(CallNode):
    def __init__(self, func, args):
        self.func = func
        self._cache = None
        self.args = args
        self._calls = 0

    def evaluate(self, frame):
        func = self.func.evaluate(frame)
        if self._cache is None:
            self._cache = func
        elif func != self._cache:
            node = DynamicCallNode(self.func, self.args)
            self._parent.replace_child(self, node)
            return node.evaluate(frame)

        self._calls += 1
        if self._calls > 4:
            return self.inline(func).evaluate(frame)
        # TODO consider inlining

        args = [a.evaluate(frame) for a in self.args]
        inner = Frame(frame, args)
        return func.evaluate(inner)

    def inline(self, func):
        #assert self._cache == func
        # TODO generate inlined node which computes args, pushes to stack
        # TODO copy original AST of func
        # TODO replace name lookups with arg lookups
        # TODO heuristic to avoid infinitely recursive inlining
        self._parent.replace_child(self, node)
        return node


class DynamicCallNode(CallNode):
    def __init__(self, func, args):
        self.func = func
        self.args = args

    def evaluate(self, frame):
        func = self.func.evaluate(frame)
        args = [a.evaluate(frame) for a in self.args]
        inner = Frame(frame, args)
        return func.evaluate(inner)


class BlockNode(Tree):
    type = Type.BLOCK

    def __init__(self, nodes):
        assert isinstance(nodes, list)
        for node in nodes:
            assert isinstance(node, Tree)
        self.nodes = nodes

    def __repr__(self):
        return "BlockNode({!r})".format(self.nodes)

    def sexpr(self):
        indent = "  "
        inner = "\n".join([a.sexpr() for a in self.nodes])
        inner = indent + ("\n" + indent).join(inner.split("\n"))
        return "{\n" + inner + "\n}"
    
    def evaluate(self):
        value = None
        for node in self.nodes:
            value = node.evaluate()
        return value


class QuoteNode(Tree):
    def __init__(self, child, type_):
        assert isinstance(child, Tree)
        self.child = child
        assert isinstance(type_, Type)
        self.type = type_

    def __repr__(self):
        return "QuoteNode({!r})".format(self.child)

    def sexpr(self):
        return "(quote " + self.child.sexpr() + ")"

    def evaluate(self):
        return self.child


#------------------------------------------------------------------------------

LET = Name(Type.FUNC, "let")
DEFINE = Name(Type.FUNC, "define")


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

    #jitdriver.jit_merge_point(node=node, scope=scope)

    if isinstance(node, CallNode):
        return eval_call(node.func, node.args, scope)
    elif isinstance(node, Name):
        return scope.lookup(node)
    elif isinstance(node, BlockNode):
        return eval_block(node, scope)
    elif isinstance(node, Closure):
        assert False, node
    elif isinstance(node, QuoteNode):
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
    from .builtins import W_Builtin

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
        assert isinstance(body, BlockNode)
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


