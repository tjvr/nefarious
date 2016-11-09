
import math
import struct
import time

try:
    from rpython.rlib.objectmodel import we_are_translated
    from rpython.rlib.rrandom import Random
except ImportError:
    def we_are_translated(): return False
    from random import Random

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
        #self._parent = None # TODO omit
        parent.replace_child(self, other)
        other._parent = parent

    def replace_child(self, child, other):
        raise NotImplementedError, self

    def evaluate(self, frame):
        raise NotImplementedError

    def copy(self):
        raise NotImplementedError, self

    def children(self):
        raise NotImplementedError, self


# TODO annotate nodes with SourceSections

class Block(Node):
    # TODO W_Block ??

    def __init__(self, nodes):
        assert isinstance(nodes, list)
        self.nodes = nodes
        for node in nodes:
            #if isinstance(node, Value) and not isinstance(node, Node):
            #    node = Literal(node)
            assert isinstance(node, Node), node
            node.set_parent(self)

    def children(self):
        return self.nodes

    def copy(self):
        return Block([n.copy() for n in self.nodes])

    def replace_child(self, child, other):
        for index in range(len(self.nodes)):
            if self.nodes[index] is child:
                self.nodes[index] = other
                return
        assert False

    def __repr__(self):
        return "Block({!r})".format(self.nodes)

    def sexpr(self):
        indent = "  "
        inner = "\n".join([a.sexpr() for a in self.nodes])
        inner = indent + ("\n" + indent).join(inner.split("\n"))
        return "{\n" + inner + "\n}"

    def evaluate(self, frame): # TODO OPT ??
        value = None
        for node in self.nodes:
            value = node.evaluate(frame)
        return value


class Literal(Node):
    def __init__(self, value, type_):
        self._parent = None
        assert isinstance(value, Value)
        assert not isinstance(value, Node)
        self.value = value
        self.type = type_

    def copy(self): return Literal(self.value, self.type)
    def children(self): return []

    def __repr__(self):
        return "Literal({!r})".format(self.value)

    def sexpr(self):
        return self.value.sexpr()

    def evaluate(self, frame):
        return self.value


class ListLiteral(Node):
    def __init__(self, items, type_):
        self._parent = None
        assert isinstance(items, list)
        self.items = items
        self.type = type_
        for item in items:
            item.set_parent(self)

    def copy(self): return ListLiteral([n.copy() for n in self.items], self.type)
    def children(self): return self.items

    def replace_child(self, child, other):
        index = self.items.index(child)
        self.items[index] = other

    def __repr__(self):
        return "ListLiteral({!r})".format(self.items)

    def sexpr(self):
        return "(list " + " ".join([n.sexpr() for n in self.items]) + ")" # TODO

    def evaluate(self, frame):
        return W_List([item.evaluate(frame) for item in self.items])


class RecordLiteral(Node):
    type = Type.get('Record')

    def __init__(self, keys, values, type_):
        self._parent = None
        self.keys = keys
        self.values = values
        self.type = type_
        for item in keys:
            assert isinstance(item, Symbol)
        for item in values:
            item.set_parent(self)

    def copy(self): return RecordLiteral(self.keys, [n.copy() for n in self.values], self.type)
    def children(self): return self.keys + self.values

    def replace_child(self, child, other):
        index = self.values.index(child)
        self.values[index] = other

    def __repr__(self):
        return "RecordLiteral({!r})".format(self.keys, self.values)

    def sexpr(self):
        items = []
        for i in range(len(self.keys)):
            items.append(self.keys[i])
            items.append(self.values[i])
        return "(record " + " ".join([n.sexpr() for n in items]) + ")"

    def evaluate(self, frame):
        values = [item.evaluate(frame) for item in self.values]
        return W_Record(self.keys, values)




class Load(Node):
    def __init__(self, name, type_):
        self._parent = None
        assert isinstance(name, Name)
        self.name = name
        self.type = type_

    def copy(self): return Load(self.name, self.type)
    def children(self): return []

    def __repr__(self):
        return "Load({!r})".format(self.name)

    def children(self): return []

    def evaluate(self, frame):
        shape = frame.shape
        index = shape.lookup(self.name)
        if index == -1: # upvalue? TODO opt
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
        # shape guard
        if frame.shape is not self.shape:
            # Ugh. frame could have added stuff to shape since last time...
            if frame.shape.compatible(self.shape):
                self.shape = frame.shape
            else:
                frame._print()
                #print self.shape.names
                #print frame.shape.names
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

    def copy(self): return Let(self.name, self.value.copy())
    def children(self): return [self.value]

    def __repr__(self):
        return "Let({!r}, {!r})".format(self.name, self.value)

    def replace_child(self, child, other):
        assert child is self.value
        self.value = other

    def evaluate(self, frame):
        value = self.value.evaluate(frame)
        frame.set(self.name, value)
    # TODO opt

    def sexpr(self):
        return "(let " + self.name.sexpr() + " " + self.value.sexpr() + ")"


class NewCell(Node):
    type = Internal.get('Var')

    def __init__(self, name):
        self.name = name

    def copy(self): return NewCell(self.name)
    def children(self): return []

    def sexpr(self):
        return "(var " + self.name.sexpr() + ")"

    def evaluate(self, frame):
        cell = W_Var(Value.NULL)
        frame.set(self.name, cell)
        return cell
    # TODO opt


class DeclareCell(Node):
    def __init__(self, name, value):
        self.name = name
        self.value = value
        value.set_parent(self)

    def copy(self): return DeclareCell(self.name, self.value.copy())
    def children(self): return [self.value]

    def replace_child(self, child, other):
        assert child == self.value
        self.value = other

    def sexpr(self):
        return "(declare " + self.name.sexpr() + " " + self.value.sexpr() + ")"

    def evaluate(self, frame):
        value = self.value.evaluate(frame)
        cell = W_Var(value)
        cell.set(value)
        frame.set(self.name, cell)
    # TODO opt


class LoadCell(Node):
    def __init__(self, name, type_):
        self.name = name
        self.type = type_

    def copy(self): return LoadCell(self.name, self.type)
    def children(self): return []

    def sexpr(self):
        return "(get " + self.name.sexpr() + ")"

    def evaluate(self, frame):
        cell = frame.lookup(self.name)
        assert isinstance(cell, W_Var)
        value = cell.get()
        # TODO check Var read is correct type
        return value
    # TODO opt


class StoreCell(Node):
    def __init__(self, name, value):
        self.name = name
        self.value = value
        value.set_parent(self)

    def copy(self): return StoreCell(self.name, self.value.copy())
    def children(self): return [self.value]

    def replace_child(self, child, other):
        assert child == self.value
        self.value = other

    def sexpr(self):
        return "(set " + self.name.sexpr() + " " + self.value.sexpr() + ")"

    def evaluate(self, frame):
        cell = frame.lookup(self.name)
        assert isinstance(cell, W_Var)
        value = self.value.evaluate(frame)
        if value is None: value = Value.NULL # TODO move this elsewhere
        cell.set(value)
    # TODO opt


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

    def copy(self): return Lambda(Func(self.func.shape.names_list(), self.func.body.copy()))
    def children(self): return [self.func.body]

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
        self.type = type_
        func.set_parent(self)
        for arg in args:
            assert isinstance(arg, Node)
            arg.set_parent(self)
        self.type = type_

    def copy(self): return Call(self.func.copy(), [a.copy() for a in self.args], self.type)
    def children(self): return [self.func] + self.args

    def sexpr(self):
        return "(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"

    def replace_child(self, child, other):
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
        except ReturnValue as ret: # TODO opt
            return ret.value

    def sexpr(self):
        return "(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"



class Apply(Node):
    def __init__(self, func, arg_list, type_):
        self._parent = None
        self.func = func
        self.arg_list = arg_list
        func.set_parent(self)
        arg_list.set_parent(self)
        self.type = type_

    def replace_child(self, child, other):
        if child is self.func:
            self.func = other
            return
        if child is self.arg_list:
            self.arg_list = other
            return
        assert False, "child not found"

    def evaluate(self, frame):
        closure = self.func.evaluate(frame)
        assert isinstance(closure, W_Func)

        arg_list = self.arg_list.evaluate(frame)
        assert isinstance(arg_list, list)

        inner = closure.call(arg_list)
        try:
            return closure.func.body.evaluate(inner)
        except ReturnValue as ret:
            return ret.value

    def sexpr(self):
        return "(apply " + self.func.sexpr() + " " + self.arg_list.sexpr() + ")"



class Return(Node):
    def __init__(self, child):
        self._parent = None
        self.child = child
        child.set_parent(self)

    def copy(self): return Return(self.child.copy())
    def children(self): return [self.child]

    def replace_child(self, child, other):
        assert child is self.child
        self.child = other

    def evaluate(self, frame):
        value = self.child.evaluate(frame)
        raise ReturnValue(value)

    def sexpr(self):
        return "(return " + self.child.sexpr() + ")"


class GetAttr(Node):
    type = Generic.ALPHA
    def __init__(self, symbol, record):
        self._parent = None
        self.symbol = symbol
        self.record = record
        record.set_parent(self)

    def copy(self): return GetAttr(self.symbol, self.record.copy())
    def children(self): return [self.record]

    def replace_child(self, record, other):
        assert record is self.record
        self.record = other

    def evaluate(self, frame):
        record = self.record.evaluate(frame)
        return self.evaluate_record(record)

    def evaluate_record(self, record):
        assert isinstance(record, W_Record)
        shape = record.shape
        index = shape.lookup(self.symbol)
        other = GetAttrOffset(self.symbol, self.record, shape, index)
        self._replace(other)
        return other.evaluate_record(record)

    def sexpr(self):
        return "(get-attr " + self.record.sexpr() + " " + self.symbol.sexpr() + ")"

class GetAttrOffset(GetAttr):
    def __init__(self, symbol, record, shape, index):
        GetAttr.__init__(self, symbol, record)
        self.shape = shape
        self.index = index

    def evaluate_record(self, record):
        # shape guard
        if record.shape is not self.shape:
            other = GetAttrGeneric(self.symbol, self.record)
            return other.evaluate_record(record)
        return record.values[self.index]

class GetAttrGeneric(GetAttr):
    def evaluate_record(self, record):
        return record.lookup(self.symbol)


class SetAttr(Node):
    def __init__(self, symbol, record, value):
        self._parent = None
        self.symbol = symbol
        self.record = record
        record.set_parent(self)
        self.value = value
        value.set_parent(self)

    def copy(self): return SetAttr(self.symbol, self.record.copy(), self.value.copy())
    def children(self): return [self.record, self.value]

    def replace_child(self, child, other):
        if child is self.record:
            self.record = other
        elif child is self.value:
            self.value = other
        else:
            assert False

    def evaluate(self, frame):
        record = self.record.evaluate(frame)
        assert isinstance(record, W_Record)
        # TODO specialise for shape
        value = self.value.evaluate(frame)
        record.set(self.symbol, value)

    def sexpr(self):
        return "(set-attr " + self.record.sexpr() + " " + self.symbol.sexpr() + " " + self.value.sexpr() + ")"


