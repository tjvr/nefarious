
import math
import struct
import time

try:
    from rpython.rlib.objectmodel import we_are_translated
    from rpython.rlib.debug import make_sure_not_resized
    from rpython.rlib.rrandom import Random
except ImportError:
    def we_are_translated(): return False
    from random import Random

#------------------------------------------------------------------------------

try:
    from rpython.rlib.jit import JitDriver
except ImportError:
    raise
    # Dummy class for running under standard CPython
    #class JitDriver(object):
    #    def __init__(self,**kw): pass
    #    def jit_merge_point(**kw): pass
    #    def can_enter_jit(self,**kw): pass

def jitpolicy(driver):
    from rpython.jit.codewriter.policy import JitPolicy
    return JitPolicy()


def get_location(node):
    return node.sexpr()


# greens: loop constants. identify loop.                eg. code object & instruction pointer
# reds: everything else used in the execution loop.     eg. frame object & execution context
call_driver = JitDriver(
    greens = ['self'],
    virtualizables = ['frame'],
    reds = ['arguments', 'func', 'scope', 'frame'],
    is_recursive = True,
    get_printable_location = get_location,
    #should_unroll_one_iteration = lambda self: True, # may or may not be necessary?
)


#------------------------------------------------------------------------------

from .types import *
from .values import *

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

    @jit.unroll_safe
    def evaluate(self, frame):
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
    def children(self): return self.values

    def replace_child(self, child, other):
        index = self.values.index(child)
        self.values[index] = other

    def __repr__(self):
        return "RecordLiteral({!r})".format(self.keys, self.values)

    def sexpr(self):
        strings = []
        for i in range(len(self.keys)):
            strings.append(self.keys[i].sexpr()) # Symbol
            strings.append(self.values[i].sexpr()) # Node
        return "(record " + " ".join(strings) + ")"

    def evaluate(self, frame):
        values = [item.evaluate(frame) for item in self.values]
        return W_Record(self.keys, values)




class Load(Node):
    def __init__(self, name, type_):
        self._parent = None
        assert isinstance(name, Name)
        self.name = name
        self.type = type_
        self.index = -1
        self.depth = -1

    def compile(self, stack):
        for depth in range(len(stack)):
            shape = stack[len(stack) - depth - 1]
            index = shape.lookup(self.name)
            if index != -1:
                self.index = index
                self.depth = depth
                break
        else:
            raise ValueError(self.name)

    def copy(self): return Load(self.name, self.type)
    def children(self): return []

    def __repr__(self):
        return "Load({!r})".format(self.name)

    def children(self): return []

    # TODO are lookups elidable?
    @jit.unroll_safe
    def evaluate(self, frame):
        #assert frame.shape is self.shape # DEBUG
        for i in range(self.depth):
            frame = frame.parent
        #assert frame, self.depth
        #assert frame.shape.lookup(self.name) == self.index, self.sexpr() # DEBUG
        return frame.lookup_offset(self.index)

    def sexpr(self):
        return self.name.sexpr()


class Let(Node):
    """For let-bindings"""
    def __init__(self, name, value):
        self._parent = None
        assert isinstance(name, Name)
        self.name = name

        self.value = value
        value.set_parent(self)
        self.index = -1

    def compile(self, stack):
        self.value.compile(stack)

        shape = stack.pop()
        self.index, shape = shape.lookup_or_insert(self.name)
        stack.append(shape)

    def copy(self): return Let(self.name, self.value.copy())
    def children(self): return [self.value]

    def __repr__(self):
        return "Let({!r}, {!r})".format(self.name, self.value)

    def replace_child(self, child, other):
        assert child is self.value
        self.value = other

    def evaluate(self, frame):
        value = self.value.evaluate(frame)
        assert frame.shape.lookup(self.name) == self.index # DEBUG
        frame.set_offset(self.index, value)

    def sexpr(self):
        return "(let " + self.name.sexpr() + " " + self.value.sexpr() + ")"


class NewCell(Node):
    type = Internal.get('Var')

    def __init__(self, name):
        self._parent = None
        self.name = name
        self.index = -1

    def compile(self, stack):
        shape = stack.pop()
        self.index, shape = shape.lookup_or_insert(self.name)
        stack.append(shape)

    def copy(self): return NewCell(self.name)
    def children(self): return []

    def sexpr(self):
        return "(var " + self.name.sexpr() + ")"

    def evaluate(self, frame):
        if self.index == -1:
            raise ValueError("NewCell was not compiled")
        cell = W_Var(Value.NULL)
        frame.set_offset(self.index, cell)
        return cell


class LoadCell(Node):
    def __init__(self, cell, type_):
        assert isinstance(cell, Node)
        self.cell = cell
        self.type = type_

    def copy(self): return LoadCell(self.cell, self.type)
    def children(self): return [self.cell]

    def sexpr(self):
        return "(get " + self.cell.sexpr() + ")"

    def evaluate(self, frame):
        cell = self.cell.evaluate(frame)
        assert isinstance(cell, W_Var)
        value = cell.get()
        # TODO check Var read is correct type
        return value


class StoreCell(Node):
    def __init__(self, cell, value):
        self.cell = cell
        cell.set_parent(self)
        self.value = value
        value.set_parent(self)

    def copy(self): return StoreCell(self.cell, self.value.copy())
    def children(self): return [self.cell, self.value]

    def replace_child(self, child, other):
        if child is self.value:
            self.value = other
        elif child is self.cell:
            self.cell = other
        else:
            assert False

    def sexpr(self):
        return "(set " + self.cell.sexpr() + " " + self.value.sexpr() + ")"

    def evaluate(self, frame):
        cell = self.cell.evaluate(frame)
        assert isinstance(cell, W_Var)
        value = self.value.evaluate(frame)
        if value is None: value = Value.NULL # TODO move this elsewhere
        cell.set(value)


class Define(Node):
    """A little like `let rec` I suppose"""
    def __init__(self, name, func):
        self._parent = None
        assert isinstance(name, Name)
        self.name = name
        self.func = func
        self.index = -1

    def compile(self, stack):
        shape = stack.pop()
        self.index, shape = shape.lookup_or_insert(self.name)
        stack.append(shape)

        shape = self.func.shape
        stack.append(shape)
        self.func.body.compile(stack)
        self.func.shape = stack.pop()

    def evaluate(self, frame):
        closure = W_Func(frame, self.func)
        assert frame.shape.lookup(self.name) == self.index # DEBUG
        frame.set_offset(self.index, closure)
        return None

    def sexpr(self):
        return "(define " + self.name.sexpr() + " " + self.func.sexpr() + ")"


class Lambda(Node):
    type = Type.FUNC

    def __init__(self, func):
        self._parent = None
        assert isinstance(func, Func)
        self.func = func

    def compile(self, stack):
        shape = self.func.shape
        stack.append(shape)
        self.func.body.compile(stack)
        self.func.shape = stack.pop()

    def copy(self): return Lambda(Func(self.func.shape.names_list(), self.func.body.copy()))
    def children(self): return [self.func.body]

    def evaluate(self, frame):
        closure = W_Func(frame, self.func)
        return closure

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

    @jit.unroll_safe
    def evaluate(self, frame):
        closure = self.func.evaluate(frame)
        assert isinstance(closure, W_Func)
        scope = closure.scope
        func = closure.func
        assert len(self.args) == func.arg_length

        arguments = [arg.evaluate(frame) for arg in self.args]

        return self.evaluate_arguments(arguments, scope, func)

    @jit.unroll_safe
    def evaluate_arguments(self, arguments, scope, func):
        make_sure_not_resized(arguments)

        frame = Frame(scope, func.shape)
        for index, value in enumerate(arguments):
            frame.set_offset(index, value)

        call_driver.jit_merge_point(self=self, frame=frame, scope=scope, func=func, arguments=arguments)

        try:
            result = func.body.evaluate(frame)
        except ReturnValue as ret: # TODO opt
            result = ret.value
        return result

    def sexpr(self):
        return "(" + self.func.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"



# class Apply(Node):
#     def __init__(self, func, arg_list, type_):
#         self._parent = None
#         self.func = func
#         self.arg_list = arg_list
#         func.set_parent(self)
#         arg_list.set_parent(self)
#         self.type = type_
# 
#     def replace_child(self, child, other):
#         if child is self.func:
#             self.func = other
#             return
#         if child is self.arg_list:
#             self.arg_list = other
#             return
#         assert False, "child not found"
# 
#     def evaluate(self, frame):
#         closure = self.func.evaluate(frame)
#         assert isinstance(closure, W_Func)
# 
#         arg_list = self.arg_list.evaluate(frame)
#         assert isinstance(arg_list, list)
# 
#         inner = closure.call(arg_list)
#         try:
#             return closure.func.body.evaluate(inner)
#         except ReturnValue as ret:
#             return ret.value
# 
#     def sexpr(self):
#         return "(apply " + self.func.sexpr() + " " + self.arg_list.sexpr() + ")"



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
        assert isinstance(record, W_Record)
        return self.evaluate_record(record)

    def evaluate_record(self, record):
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
        value = self.value.evaluate(frame)
        return self.evaluate_record(record, value)

    def evaluate_record(self, record, value):
        shape = record.shape
        index = shape.lookup(self.symbol)
        other = SetAttrOffset(self.symbol, self.record, self.value, shape, index)
        self._replace(other)
        return other.evaluate_record(record, value)

    def sexpr(self):
        return "(set-attr " + self.record.sexpr() + " " + self.symbol.sexpr() + " " + self.value.sexpr() + ")"

class SetAttrOffset(SetAttr):
    def __init__(self, symbol, record, value, shape, index):
        SetAttr.__init__(self, symbol, record, value)
        self.shape = shape
        self.index = index

    def evaluate_record(self, record, value):
        # shape guard
        if record.shape is not self.shape:
            other = SetAttrGeneric(self.symbol, self.record, self.value)
            return other.evaluate_record(record, value)
        record.values[self.index] = value

class SetAttrGeneric(SetAttr):
    def evaluate_record(self, record, value):
        record.set(self.symbol, value)

