
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
        parent.replace(self, other)
        other._parent = parent

    def replace(self, child, other):
        raise NotImplementedError

    def evaluate(self, frame):
        raise NotImplementedError

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

    def replace(self, child, other):
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
        self._parent = None
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


class ListLiteral(Node):
    def __init__(self, items, type_):
        self._parent = None
        assert isinstance(items, list)
        self.items = items
        self.type = type_

    def __repr__(self):
        return "ListLiteral({!r})".format(self.items)

    def sexpr(self):
        return "(list " + " ".join([n.sexpr() for n in self.items]) + ")" # TODO

    def evaluate(self, frame):
        return W_List([item.evaluate(frame) for item in self.items])


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


class NewCell(Node):
    type = Internal.get('Var')

    def __init__(self, name):
        self.name = name

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

    def replace(self, child, other):
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

    def replace(self, child, other):
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

    def evaluate(self, frame):
        closure = W_Func(frame, self.func)
        return closure

    # TODO opt?? cache Closures?

    def sexpr(self):
        return "(fun " + self.func.sexpr() + ")"


class Call(Node):
    def __init__(self, func, args, type_):
        # TODO handle Repeat better
        args = [(ListLiteral(arg.items, _List) if isinstance(arg, W_List) else arg) for arg in args]

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

    def evaluate(self, frame): # TODO OPT
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

class Apply(Node):
    def __init__(self, func, arg_list, type_):
        self._parent = None
        self.func = func
        self.arg_list = arg_list
        func.set_parent(self)
        arg_list.set_parent(self)
        self.type = type_

    def replace(self, child, other):
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



class Builtin(Node):
    type = None

    def __init__(self, args, type_):
        raise NotImplementedError

    def sexpr(self):
        return "(" + self.__class__.__name__ + " " + " ".join([a.sexpr() for a in self._args()]) + ")"

class UnaryBuiltin(Builtin):
    def __init__(self, args, type_):
        self._parent = None
        self.child, = args
        self.child.set_parent(self)
    def _args(self):
        return [self.child]
    def replace(self, child, other):
        if child == self.child:
            self.child = other
        else:
            assert False


class InfixBuiltin(Builtin):
    def __init__(self, args, type_):
        self._parent = None
        self.left, self.right = args
        self.left.set_parent(self)
        self.right.set_parent(self)
    def _args(self):
        return [self.left, self.right]
    def replace(self, child, other):
        if child == self.left:
            self.left = child
        elif child == self.right:
            self.right = child
        else:
            assert False


Bool = Type.get('Bool')

class BOOL_NOT(UnaryBuiltin):
    type = Bool
    arg_types = [Bool]
    def evaluate(self, frame):
        child = self.child.evaluate(frame)
        if child is Value.TRUE:
            return Value.FALSE
        elif child is Value.FALSE:
            return Value.TRUE
        assert False

class BOOL_OR(InfixBuiltin):
    type = Bool
    arg_types = [Bool, Bool]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        if left is Value.TRUE:
            return Value.TRUE
        assert left is Value.FALSE
        right = self.right.evaluate(frame)
        if right is Value.TRUE:
            return Value.TRUE
        assert right is Value.FALSE
        return Value.FALSE

class BOOL_AND(InfixBuiltin):
    type = Bool
    arg_types = [Bool, Bool]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        if left is Value.FALSE:
            return Value.FALSE
        assert left is Value.TRUE
        right = self.right.evaluate(frame)
        if right is Value.FALSE:
            return Value.FALSE
        assert right is Value.TRUE
        return Value.TRUE


Int = Type.get('Int')

class INT_ADD(InfixBuiltin):
    type = Int
    arg_types = [Int, Int]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Int(left.value.add(right.value))

class INT_SUB(InfixBuiltin):
    type = Int
    arg_types = [Int, Int]
    def evaluate(self, frame): # this is expensive
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Int(left.value.sub(right.value))

# TODO INT_EQ

class INT_LT(InfixBuiltin):
    type = Bool
    arg_types = [Int, Int]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Bool.get(left.value.lt(right.value))

class INT_RANDOM(InfixBuiltin):
    type = Int
    arg_types = [Int, Int]

    random = Random(seed=int(time.time()))

    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        # TODO random for bigints.
        start = left.value.toint()
        end = right.value.toint()
        f = INT_RANDOM.random.random()
        value = int(0.5 + start + f * (end - start))
        return W_Int.fromint(value)

class INT_FLOAT(UnaryBuiltin):
    type = Type.get('Float')
    arg_types = [Int]
    def evaluate(self, frame):
        child = self.child.evaluate(frame)
        assert isinstance(child, W_Int)
        return W_Float(child.value.tofloat())



Float = Type.get('Float')

class FLOAT_ADD(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float), left
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.value + right.value)
    # TODO evaluate_float

class FLOAT_SUB(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.value - right.value)
    # TODO evaluate_float

class FLOAT_LT(InfixBuiltin):
    type = Bool
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Bool.get(left.value < right.value)
    # TODO evaluate_float

class FLOAT_ROUND(UnaryBuiltin):
    type = Int
    arg_types = [Float]
    def evaluate(self, frame):
        f = self.child.evaluate(frame)
        assert isinstance(f, W_Float)
        return W_Int.fromfloat(f.value + 0.5)
    # TODO evaluate_float





Text = Type.get('Text')

class TEXT_JOIN(UnaryBuiltin):
    type = Text
    arg_types = [List.get(Text)]
    def evaluate(self, frame):
        text_list = self.child.evaluate(frame)
        return W_Text.join(text_list)

class TEXT_SPLIT(UnaryBuiltin):
    type = List.get(Text)
    arg_types = [Text]
    def evaluate(self, frame):
        text = self.child.evaluate(frame)
        return text.split()

class TEXT_JOIN_WITH(InfixBuiltin):
    type = Text
    arg_types = [List.get(Text), Text]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        right = self.right.evaluate(frame)
        return W_Text.join_with(left, right)

class TEXT_SPLIT_BY(InfixBuiltin):
    type = List.get(Text)
    arg_types = [Text, Text]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        right = self.right.evaluate(frame)
        return left.split_by(right)



Bytes = Type.get('Bytes')

# class BYTES_URANDOM(Builtin):
#         context = INT_RANDOM.random_context
#         try:
#             bytes_ = W_Int.fromint(rurandom.urandom(context, 4))
#         except OSError as e:
#             raise # TODO



_a = Generic.ALPHA
_Block = Type.get('Block')
_Line = Internal.get('Line')

class IF_THEN_ELSE(Builtin):
    type = _a
    arg_types = [Bool, _a, _a]

    def __init__(self, values, type_):
        self.cond, self.tv, self.fv = values
        self.cond.set_parent(self)
        self.tv.set_parent(self)
        self.fv.set_parent(self)

    def sexpr(self):
        return "(IF_THEN_ELSE " + self.cond.sexpr() + " " + self.tv.sexpr() + " " + self.fv.sexpr() + ")"

    def evaluate(self, frame): # TODO OPT
        cond = self.cond.evaluate(frame)
        if cond == Value.TRUE:
            return self.tv.evaluate(frame)
        elif cond == Value.FALSE:
            return self.fv.evaluate(frame)
        assert False

class WHILE(Builtin):
    # TODO move to preamble
    type = _Line
    arg_types = [Bool, _Block]

    def __init__(self, values, type_):
        self.cond, body = values
        self.cond.set_parent(self)
        assert isinstance(body, Lambda)
        self.body = body.func.body
        self.body.set_parent(self)

    def sexpr(self):
        return "(WHILE " + self.cond.sexpr() + " " + self.body.sexpr() + ")"

    def evaluate(self, frame):
        cond = self.cond.evaluate(frame)
        while cond is Value.TRUE:
            self.body.evaluate(frame)
            cond = self.cond.evaluate(frame)
        assert cond is Value.FALSE


_List = List.get(_a)

class LIST_ADD(InfixBuiltin):
    type = _Line
    arg_types = [_List.get(_a), _a]
    def evaluate(self, frame):
        list_ = self.left.evaluate(frame)
        item = self.right.evaluate(frame)
        assert isinstance(list_, W_List)
        list_.items.append(item)

class LIST_GET(InfixBuiltin):
    type = _a
    arg_types = [_List.get(_a), Int]
    def evaluate(self, frame):
        list_ = self.left.evaluate(frame)
        assert isinstance(list_, W_List)
        int_ = self.right.evaluate(frame)
        assert isinstance(int_, W_Int)
        index = int_.value.toint()
        if not 1 <= index <= len(list_.items):
            raise IndexError(index) # TODO error handling
        return list_.items[index - 1]

class LIST_LEN(UnaryBuiltin):
    type = Int
    arg_types = [_List.get(_a)]
    def evaluate(self, frame):
        list_ = self.child.evaluate(frame)
        assert isinstance(list_, W_List)
        return W_Int.fromint(len(list_.items))

