
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

class Node(Tree):
    type = None

    def set_parent(self, parent):
        self._parent = parent

    def _replace(self, other):
        assert isinstance(other, Node)
        parent = self._parent
        self._parent = None
        parent.replace(self, other)
        other._parent = parent

    def replace(self, child, other):
        raise NotImplementedError

    def evaluate(self, frame):
        raise NotImplementedError

        
class Block(Node):
    # TODO W_Block ??

    def __init__(self, nodes):
        assert isinstance(nodes, list)
        for node in nodes:
            assert isinstance(node, Node), node
            node.set_parent(self)
        self.nodes = nodes

    def replace(self, child, other):
        for index in range(len(self.nodes)):
            if self.nodes[index] is child:
                self.nodes[index] = other
                return
        assert False

    def __repr__(self):
        return "BlockNode({!r})".format(self.nodes)

    def sexpr(self):
        indent = "  "
        inner = "\n".join([a.sexpr() for a in self.nodes])
        inner = indent + ("\n" + indent).join(inner.split("\n"))
        return "{\n" + inner + "\n}"
    
    def evaluate(self, frame):
        value = None
        for node in self.nodes:
            value = node.evaluate(frame)
        return value
    

class Quote(Node):
    def __init__(self, child):
        assert isinstance(child, Node)
        self.child = child
        #child.set_parent(self)

    def replace(self, child, other):
        assert False
        # assert child is self.child
        # self.child = other

    def __repr__(self):
        return "Quote({!r})".format(self.child)

    def sexpr(self):
        return "(quote " + self.child.sexpr() + ")"

    def evaluate(self, frame):
        return self.child # !!!


class Literal(Node):
    def __init__(self, value, type_):
        assert isinstance(value, Value)
        assert not isinstance(value, Node)
        self.value = value
        self.type = type_

    def __repr__(self):
        return "Literal({!r})".format(self.value)

    def sexpr(self):
        return self.value.sexpr()

    def evaluate(self, frame):
        return self.value


class Load(Node):
    def __init__(self, name, type_):
        self._parent = None
        assert isinstance(name, Name)
        self.name = name
        self.type = type_

    def __repr__(self):
        return "Load({!r})".format(self.name)

    def evaluate(self, frame):
        shape = frame.shape
        index = shape.lookup(self.name)
        if index == -1: # upvalue?
            other = LoadGeneric(self.name)
        else:
            other = LoadOffset(self.name, shape, index)
        self._replace(other)
        return other.evaluate(frame)

    def sexpr(self):
        return self.name.sexpr()

class LoadOffset(Load):
    def __init__(self, name, shape, index):
        self._parent = None
        self.name = name
        self.shape = shape
        self.index = index

    def evaluate(self, frame):
        if frame.shape is not self.shape: # shape guard
            assert False # ???
            other = LoadGeneric(self.name)
            self._replace(other)
            return other.evaluate(frame)
        return frame.values[self.index]

class LoadGeneric(Load):
    def __init__(self, name):
        self.name = name
    def evaluate(self, frame):
        return frame.lookup(self.name)


class Let(Node):
    """For let-bindings"""
    def __init__(self, name, value):
        self._parent = None
        assert isinstance(name, Name)
        self.name = name

        self.value = value
        value.set_parent(self)

    def __repr__(self):
        return "Let({!r}, {!r})".format(self.name, self.value)

    def replace(self, child, other):
        assert child is self.value
        self.value = other

    def evaluate(self, frame):
        value = self.value.evaluate(frame)
        frame.set(self.name, value)
    # TODO opt

    # TODO evaluate_float

    def sexpr(self):
        return "(let " + self.name.sexpr() + " " + self.value.sexpr() + ")"


class Define(Node):
    """A little like `let rec` I suppose"""
    def __init__(self, name, func):
        self._parent = None
        assert isinstance(name, Name)
        self.name = name
        self.func = func

    def evaluate(self, frame):
        closure = W_Func(frame, self.func)
        frame.set(self.name, closure)
        return None
    # TODO opt?? cache Closures?

    def sexpr(self):
        return "(define " + self.name.sexpr() + " " + self.func.sexpr() + ")"


class Lambda(Node):
    type = Type.FUNC

    def __init__(self, func):
        self._parent = None
        assert isinstance(func, Func)
        self.func = func

    def evaluate(self, frame):
        closure = W_Func(frame, self.func)
        return closure

    # TODO opt?? cache Closures?

    def sexpr(self):
        return "(fun " + self.func.sexpr() + ")"


class Call(Node):
    def __init__(self, func, args, type_):
        self._parent = None
        self.func = func
        self.args = args
        func.set_parent(self)
        assert isinstance(args, list)
        for arg in args:
            assert isinstance(arg, Node), arg
            arg.set_parent(self)

        self.type = type_

    def replace(self, child, other):
        if child is self.func:
            self.func = other
            return
        for index in range(len(self.args)):
            if self.args[index] is child:
                self.args[index] = other
                return
        assert False, "child not found"

    def evaluate(self, frame):
        closure = self.func.evaluate(frame)
        assert isinstance(closure, W_Func)

        arg_list = [arg.evaluate(frame) for arg in self.args]
        inner = closure.call(arg_list)
        try:
            return closure.func.body.evaluate(inner)
        except ReturnValue as ret:
            return ret.value

    def sexpr(self):
        return "(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"


class Return(Node):
    def __init__(self, child):
        self._parent = None
        self.child = child
        child.set_parent(self)

    def replace(self, child, other):
        assert child is self.child
        self.child = other

    def evaluate(self, frame):
        value = self.child.evaluate(frame)
        raise ReturnValue(value)

    def sexpr(self):
        return "(return " + self.child.sexpr() + ")"


# class StaticCall(Node):
#     def __init__(self, func, args, closure):
#         self._parent = None
#         self.func = func
#         self.args = args
#         self.closure = closure
# 
#     def evaluate(self, frame):
#         closure = self.func.evaluate()
#         if closure != self.closure:
#             other = DynamicCall(self._parent, self.func, self.args)
#             self._replace(other)
# 
#         arg_list = [arg.evaluate(frame) for arg in self.args]
#         inner = closure.call(arg_list)
#         return closure.func.body.evaluate(inner)
# 
#     # inline? TODO opt
#     # StaticNamedCall? TODO opt
# 
# class DynamicCall(Node):
#     def __init__(self, func, args):
#         self._parent = None
#         self.func = func
#         self.args = args
# 
#     def evaluate(self, frame):
#         closure = self.func.evaluate(frame)
#         assert isinstance(closure, W_Func)
# 
#         arg_list = [arg.evaluate(frame) for arg in self.args]
#         inner = closure.call(arg_list)
#         return closure.func.body.evaluate(inner)


# class LoadCell(Node):
#     def __init__(self, name, type_):
#         pass # TODO 
# 
#     def evaluate(self, frame):
#         pass # TODO check Var read is correct type
# 
# class StoreCell(Node):
#     def __init__(self, name, value):
#         pass # TODO 
# 
#     def evaluate(self, frame):
#         value = self.value.evaluate() # ...
#         pass # TODO

