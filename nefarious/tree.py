
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


def get_location(self):
    #assert isinstance(self, Node)
    return self.sexpr()


# greens: loop constants. identify loop.                eg. code object & instruction pointer
# reds: everything else used in the execution loop.     eg. frame object & execution context
call_driver = JitDriver(
    greens = ['self'],
    virtualizables = ['frame'],
    reds = ['func', 'scope', 'frame'],
    is_recursive = True,
    get_printable_location = get_location,
    should_unroll_one_iteration = lambda self: True, # may or may not be necessary?
)


#------------------------------------------------------------------------------

from .types import *
from .values import *

# TODO annotate nodes with SourceSections

class Sequence(Node):
    __slots__ = Node.__slots__ + ['nodes']
    _immutable_fields_ = ['nodes']

    def __init__(self, nodes):
        Node.__init__(self)
        assert isinstance(nodes, list)
        self.nodes = nodes
        for node in nodes:
            #if isinstance(node, Value) and not isinstance(node, Node):
            #    node = Literal(node)
            assert isinstance(node, Node), node
            node.set_parent(self)

    def _copy(self, transform): return Sequence([n.copy(transform) for n in self.nodes])
    def children(self): return self.nodes

    @classmethod
    def _test_cases(cls):
        yield Sequence([])
        yield Sequence([TEST_INT_LITERAL])

    def replace_child(self, child, other):
        for index in range(len(self.nodes)):
            if self.nodes[index] is child:
                self.nodes[index] = other
                return
        # sometimes, we can't find the child.
        # to do I think with not modifying frames executing on the stack

    def __repr__(self):
        return "Sequence({!r})".format(self.nodes)

    def sexpr(self):
        indent = "  "
        inner = "\n".join([a.sexpr() for a in self.nodes])
        inner = indent + ("\n" + indent).join(inner.split("\n"))
        return "{\n" + inner + "\n}"

    @staticmethod
    def get_items(node, out):
        if isinstance(node, Sequence):
            for item in node.nodes:
                Sequence.get_items(item, out)
        else:
            out.append(node)

    @classmethod
    def flatten(self, items):
        if len(items) == 1:
            return items[0]
        out = []
        for node in items:
            Sequence.get_items(node, out)
        return Sequence(out)

    @jit.unroll_safe
    def evaluate(self, frame):
        # TODO: rewrite to remove nested Sequences

        assert frame
        value = None
        nodes = self.nodes
        jit.promote(nodes) # assume replace_child won't happen in traced code
        for node in nodes:
            value = node.evaluate(frame)
        return value


class Literal(Node):
    __slots__ = Node.__slots__ + ['value']
    _immutable_fields_ = ['value']

    def __init__(self, value, type_):
        Node.__init__(self)
        assert isinstance(value, Value)
        assert not isinstance(value, Node)
        self.value = value
        self.type = type_

    def _copy(self, transform): return Literal(self.value, self.type)
    def children(self): return []

    @classmethod
    def _test_cases(cls):
        yield TEST_INT_LITERAL

    def __repr__(self):
        return "Literal({!r})".format(self.value)

    def sexpr(self):
        return self.value.sexpr()

    def evaluate(self, frame):
        return self.value

TEST_INT_LITERAL = Literal(W_Int.fromint(42), Type.get('Int'))

class ListLiteral(Node):
    __slots__ = Node.__slots__ + ['items']
    _immutable_fields_ = ['items']

    def __init__(self, items, type_):
        Node.__init__(self)
        assert isinstance(items, list)
        self.items = items
        self.type = type_
        for item in items:
            item.set_parent(self)

    def _copy(self, transform): return ListLiteral([n.copy(transform) for n in self.items], self.type)
    def children(self): return self.items

    @classmethod
    def _test_cases(cls):
        yield cls([TEST_INT_LITERAL], List.get(Type.get('Int')))

    def replace_child(self, child, other):
        index = self.items.index(child)
        self.items[index] = other

    def __repr__(self):
        return "ListLiteral({!r})".format(self.items)

    def sexpr(self):
        return "(list " + " ".join([n.sexpr() for n in self.items]) + ")" # TODO

    @jit.unroll_safe
    def evaluate(self, frame):
        jit.promote(self.items)
        return W_List([item.evaluate(frame) for item in self.items])


class RecordLiteral(Node):
    __slots__ = Node.__slots__ + ['keys', 'values']
    _immutable_fields_ = ['keys', 'values']
    type = Type.get('Record')

    def __init__(self, keys, values, type_):
        Node.__init__(self)
        self.keys = keys
        self.values = values
        for item in keys:
            assert isinstance(item, Symbol)
        for item in values:
            item.set_parent(self)

    def _copy(self, transform): return RecordLiteral(self.keys, [n.copy(transform) for n in self.values], self.type)
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

    @jit.unroll_safe
    def evaluate(self, frame):
        # Can't promote self.keys because it doesn't unify!
        jit.promote(self.values)
        eval_values = [item.evaluate(frame) for item in self.values]
        return W_Record(self.keys, eval_values)


class Load(Node):
    __slots__ = Node.__slots__ + ['name', 'index', 'depth']
    _immutable_fields_ = ['name', 'index', 'depth']

    def __init__(self, name, type_):
        Node.__init__(self)
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

    def _copy(self, transform): return Load(self.name, self.type)
    def children(self): return []

    @classmethod
    def _test_cases(cls):
        yield cls(Name("quxx"), Type.get('Int'))

    def __repr__(self):
        return "Load({!r})".format(self.name)

    def children(self): return []

    @jit.unroll_safe
    def evaluate(self, frame):
        depth = self.depth
        jit.promote(depth)
        for i in range(depth):
            frame = frame.parent

        index = self.index
        jit.promote(index)
        return frame.lookup(index)

    def sexpr(self):
        return self.name.sexpr()


class Let(Node):
    """For let-bindings. Works as let-rec"""
    __slots__ = Node.__slots__ + ['name', 'value', 'index']
    _immutable_fields_ = ['name', 'value', 'index']

    def __init__(self, name, value):
        Node.__init__(self)
        assert isinstance(name, Name)
        self.name = name

        self.value = value
        value.set_parent(self)
        self.index = -1

    def compile(self, stack):
        shape = stack.pop()
        self.index, shape = shape.lookup_or_insert(self.name)
        stack.append(shape)

        # let-rec: define name before compiling value.
        self.value.compile(stack)

    def _copy(self, transform): return Let(self.name, self.value.copy(transform))
    def children(self): return [self.value]

    @classmethod
    def _test_cases(cls):
        yield cls(Name("quxx"), TEST_INT_LITERAL)
        yield cls(Name("f"), Lambda([], Sequence([TEST_INT_LITERAL])))

    def __repr__(self):
        return "Let({!r}, {!r})".format(self.name, self.value)

    def replace_child(self, child, other):
        assert child is self.value
        self.value = other

    def evaluate(self, frame):
        jit.promote(self.value)
        value = self.value.evaluate(frame)
        index = self.index
        jit.promote(index)
        frame.set(index, value)

    def sexpr(self):
        return "(let " + self.name.sexpr() + " " + self.value.sexpr() + ")"



class NewCell(Node):
    type = Internal.get('Var')
    __slots__ = Node.__slots__ + ['name', 'index']
    _immutable_fields_ = ['name', 'index']

    def __init__(self, name):
        Node.__init__(self)
        self.name = name
        self.index = -1

    def compile(self, stack):
        shape = stack.pop()
        self.index, shape = shape.lookup_or_insert(self.name)
        stack.append(shape)

    def _copy(self, transform): return NewCell(self.name)
    def children(self): return []

    @classmethod
    def _test_cases(cls):
        yield cls(Name("x"))

    def sexpr(self):
        return "(var " + self.name.sexpr() + ")"

    def evaluate(self, frame):
        if self.index == -1:
            raise ValueError("NewCell was not compiled")
        index = self.index
        jit.promote(index)
        cell = W_Var(Value.NULL)
        frame.set(index, cell)
        return cell


class LoadCell(Node):
    __slots__ = Node.__slots__ + ['cell']
    _immutable_fields_ = ['cell']

    def __init__(self, cell, type_):
        Node.__init__(self)
        assert isinstance(cell, Node)
        cell.set_parent(self)
        self.cell = cell
        self.type = type_

    def _copy(self, transform): return LoadCell(self.cell.copy(transform), self.type)
    def children(self): return [self.cell]

    @classmethod
    def _test_cases(cls):
        yield cls(Load(Name("x"), Type.VAR), Type.get('Int'))

    def sexpr(self):
        return "(get " + self.cell.sexpr() + ")"

    def evaluate(self, frame):
        jit.promote(self.cell)
        cell = self.cell.evaluate(frame)
        assert isinstance(cell, W_Var)
        value = cell.get()
        # TODO check Var read is correct type
        return value


class StoreCell(Node):
    __slots__ = Node.__slots__ + ['cell', 'value']
    _immutable_fields_ = ['cell', 'value']

    def __init__(self, cell, value):
        Node.__init__(self)
        self.cell = cell
        cell.set_parent(self)
        self.value = value
        value.set_parent(self)

    def _copy(self, transform): return StoreCell(self.cell.copy(transform), self.value.copy(transform))
    def children(self): return [self.cell, self.value]

    @classmethod
    def _test_cases(cls):
        yield cls(Load(Name("x"), Type.VAR), TEST_INT_LITERAL)

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
        jit.promote(self.cell)
        cell = self.cell.evaluate(frame)
        assert isinstance(cell, W_Var)
        jit.promote(self.value)
        value = self.value.evaluate(frame)
        if value is None: value = Value.NULL # TODO move this elsewhere
        cell.set(value)


class Lambda(Node):
    type = Type.FUNC

    __slots__ = Node.__slots__ + ['body', 'original_body', 'shape', '_arg_names']
    _immutable_fields_ = ['body', 'original_body', 'shape', '_arg_names']

    def __init__(self, arg_names, body):
        Node.__init__(self)

        self.shape = Shape.get(arg_names) # map for accessing locals in Frame
        self._arg_names = arg_names

        assert isinstance(body, Node)
        self.body = body
        self.original_body = None if body is None else body.copy()

    @jit.elidable
    def arg_length(self):
        return len(self._arg_names)

    @jit.elidable
    def arg_names(self):
        return self._arg_names

    def _copy(self, transform): return Lambda(self.arg_names(), self.body.copy(transform))
    def children(self): return [self.body]

    def compile(self, stack):
        shape = self.shape
        stack.append(shape)
        self.body.compile(stack)
        self.shape = stack.pop()

    @classmethod
    def _test_cases(cls):
        yield cls([], Sequence([TEST_INT_LITERAL]))

    def evaluate(self, frame):
        return Closure(frame, self)

    def sexpr(self):
        return "(fun " + " ".join([n.name for n in self.arg_names()]) + " " + self.body.sexpr() + ")"


class Call(Node):
    __slots__ = Node.__slots__ + ['func_node', 'args', 'call_count', 'cached_func', 'cached_closure']
    _immutable_fields_ = ['func_node', 'args', 'cached_func', 'cached_closure']

    def __init__(self, func_node, args, type_, call_count=0):
        Node.__init__(self)
        assert isinstance(func_node, Node)
        #assert func_node.type == Type.FUNC
        self.func_node = func_node
        self.args = args
        self.type = type_
        func_node.set_parent(self)
        for arg in args:
            assert isinstance(arg, Node)
            arg.set_parent(self)
        self.call_count = call_count
        self.cached_func = None
        self.cached_closure = None

    @classmethod
    def _test_cases(cls):
        yield cls(Load(Name("f"), Type.FUNC), [], Type.get('Int'))
        yield cls(Load(Name("f"), Type.FUNC), [TEST_INT_LITERAL], Type.get('Int'))

    def _copy(self, transform): return Call(self.func_node.copy(transform), [a.copy(transform) for a in self.args], self.type)
    def children(self): return [self.func_node] + self.args

    def sexpr(self):
        return "(" + self.func_node.sexpr() + " " + " ".join([a.sexpr() for a in self.args]) + ")"

    def replace_child(self, child, other):
        if child is self.func_node:
            self.func_node = other
            return
        for index in range(len(self.args)):
            if self.args[index] is child:
                self.args[index] = other
                return
        assert False, "child not found"

    def evaluate(self, frame):
        func_node = self.func_node
        closure = func_node.evaluate(frame)
        assert isinstance(closure, Closure)
        func = closure.func
        self.cached_closure = closure

        # fast transition
        call_count = self.call_count
        if call_count >= 1: # 2nd call
            assert self.cached_closure
            cached_closure = self.cached_closure
            if closure is cached_closure:
                new_call = StaticCall(func_node, self.args, self.type, closure, call_count)
            elif func is cached_closure.func:
                new_call = FuncCall(func_node, self.args, self.type, func, call_count)
            else:
                new_call = GenericCall(func_node, self.args, self.type, call_count)
            self._replace(new_call)
            return new_call.evaluate_closure(frame, closure.scope, func)

        self.cached_closure = closure
        return self.evaluate_closure(frame, closure.scope, closure.func)

    @jit.unroll_safe
    def evaluate_closure(self, frame, scope, func):
        length = len(self.args)
        jit.promote(length)
        assert length == func.arg_length()

        inner = Frame(scope, func.shape, func)
        for index in range(length):
            arg = self.args[index]
            value = arg.evaluate(frame)
            inner.set(index, value)

        return self.evaluate_arguments(inner, scope, func)

    def evaluate_arguments(self, frame, scope, func):
        self.call_count += 1

        call_driver.jit_merge_point(self=self, frame=frame, scope=scope, func=func)

        body = func.body # no longer immutable...
        jit.promote(body)
        try:
            result = body.evaluate(frame)
        except ReturnValue as ret: # TODO opt
            result = ret.value
        return result


class StaticCall(Call):
    __slots__ = Call.__slots__
    _immutable_fields_ = Call._immutable_fields_

    """Call always to the same closure instance"""
    def __init__(self, func_node, args, type_, closure, call_count=0):
        Call.__init__(self, func_node, args, type_, call_count)
        assert isinstance(closure, Closure)
        self.cached_closure = closure

    @classmethod
    def _test_cases(cls):
        return [] # TODO
        # closure = None
        # yield cls(Load(Name("f"), Type.FUNC), [], Type.get('Int'), closure)
        # yield cls(Load(Name("f"), Type.FUNC), [TEST_INT_LITERAL], Type.get('Int'), closure)

    @jit.unroll_safe
    def evaluate(self, frame):
        func_node = self.func_node
        jit.promote(func_node) # nb. this could of course change
        closure = func_node.evaluate(frame)
        assert isinstance(closure, Closure)

        # guard: closure
        cached_closure = self.cached_closure
        jit.promote(cached_closure) # immutable
        jit.promote(closure)
        if closure is not cached_closure: # guard
            if closure.func is cached_closure.func:
                new_call = FuncCall(self.func_node, self.args, self.type, closure.func, self.call_count)
            else:
                new_call = GenericCall(self.func_node, self.args, self.type, self.call_count)
            self._replace(new_call)
            return new_call.evaluate_closure(frame, closure.scope, closure.func)

        # inlining
        allow_inlining = Options.INLINING
        jit.promote(allow_inlining)
        if allow_inlining:
            if self.call_count == 3: # 4th call
                if not frame.func:
                    pass # can't inline into global scope.
                elif frame.func.body.weight > 40:
                    pass # this is getting silly.
                # TODO handle recursive inlining separately?
                else:
                    self.inline_call(frame.func, frame, closure)
                    #print frame.func.body.sexpr()

        return self.evaluate_closure(frame, closure.scope, closure.func)

    def inline_arguments(self, closure_locals):
        args = self.args
        names = closure_locals[:len(args)]
        return [Let(names[i], args[i].copy()) for i in range(len(args))]

    def inline_body(self, closure, closure_args, outer_scope):
        if isinstance(self.func_node, Load):
            fn = self.func_node
            assert isinstance(fn, Load)
            closure_name = fn.name
        else:
            closure_name = Name("closure")
        assert isinstance(closure_name, Name)
        closure_node = Load(closure_name, Type.FUNC)

        # Transform closure-scope lookups in the body. source of much grief
        whitelist = outer_scope.all_names()
        for name in closure_args:
            whitelist[name] = True
        blacklist = closure.scope.all_names()
        # names in blacklist but not in whitelist
        # must be looked up via Closure instance.
        transform = ClosureLookupTransform(closure_node, whitelist, blacklist)
        body_clone = closure.func.original_body.copy(transform)

        # record whether closure lookups are used.
        if not transform.used_closure:
            closure_node = None
        return closure_node, body_clone

    def create_inlined(self, frame, closure):
        # Alpha-rename locals
        closure_locals = closure.func.shape.names_list()
        alpha_locals = [Name(n.name) for n in closure_locals]

        # Move argument evaluation into `Let`s
        items = self.inline_arguments(alpha_locals)

        # Copy body & replace closure-scope lookups.
        closure_args = closure_locals[:len(self.args)]
        closure_node, body = self.inline_body(closure, closure_args, frame)
        # TODO avoid copying body twice!
        body = body.copy(RenameTransform(closure_locals, alpha_locals))
        items.append(body)

        # avoid evaluating func_node twice.
        func_node = self.func_node.copy()
        let = None
        if closure_node:
            if isinstance(func_node, Load) and func_node.name == closure_node.name:
                pass # don't include `let`.
            else:
                let = Let(closure_node.name, func_node)
            func_node = closure_node.copy()

        inline = InlinedStatic(
            func_node,
            self.args,
            self.type,
            closure,
            Sequence(items), # TODO .flatten(items),
            self.call_count,
        )

        if let:
            return Sequence([let, inline])
        return inline

    @jit.dont_look_inside
    def inline_call(self, outer_func, frame, closure):
        # self --the Call to inline.
        # outer_func --the function the Call is inside.
        # frame --the Frame of the current function.
        # closure --the Closure we're inlining.

        inlined = self.create_inlined(frame, closure)

        # Rewrite outer_func
        transform = ReplaceTransform(replace=self, with_=inlined)
        outer_func.body = outer_func.body.copy(transform)

        # Fix outer_func's Frame shape.
        stack = frame.shape_stack()
        #stack.append(outer_func.shape)
        #assert stack[-1] == stack[-2]
        #print outer_func.body.sexpr()
        outer_func.body.compile(stack)
        #assert len(outer_func.shape.names_list()) <= stack[-1].names_list()
        outer_func.shape = stack.pop()

        b = outer_func.body
        if b._parent: b = b._parent


class InlinedStatic(StaticCall):
    __slots__ = Node.__slots__ + ['cached_closure', 'body']
    _immutable_fields_ = ['cached_closure', 'body']

    def __init__(self, func_node, args, type_, closure, body, call_count=0):
        Call.__init__(self, func_node, args, type_, call_count)
        assert isinstance(body, Sequence)
        self.cached_closure = closure
        body.set_parent(self)
        self.body = body

    def _copy(self, transform):
        return InlinedStatic(
            self.func_node.copy(transform),
            [a.copy(transform) for a in self.args],
            self.type,
            self.cached_closure,
            self.body.copy(transform)
        )
    def children(self): return [self.func_node, self.body]

    # TODO _test_cases: important!

    def sexpr(self):
        return "(INLINE " + self.func_node.sexpr() + " " + self.body.sexpr() + ")"

    def evaluate(self, frame):
        func_node = self.func_node
        jit.promote(func_node) # nb. this could of course change
        closure = func_node.evaluate(frame)
        assert isinstance(closure, Closure)

        # guard: closure
        cached_closure = self.cached_closure
        jit.promote(cached_closure) # immutable
        jit.promote(closure)
        if closure is not cached_closure: # guard
            if closure.func is cached_closure.func:
                new_call = FuncCall(self.func_node, self.args, self.type, closure.func, self.call_count)
            else:
                new_call = GenericCall(self.func_node, self.args, self.type, self.call_count)
            self._replace(new_call)
            return new_call.evaluate_closure(frame, closure.scope, closure.func)

        return self.body.evaluate(frame)


class FuncCall(Call):
    """Call always to the same func body (but different closure scopes!)"""
    def __init__(self, func_node, args, type_, func, call_count=0):
        Call.__init__(self, func_node, args, type_, call_count)
        assert isinstance(func, Lambda)
        self.cached_func = func

    @classmethod
    def _test_cases(cls):
        func = Lambda([], Sequence([TEST_INT_LITERAL]))
        yield cls(Load(Name("f"), Type.FUNC), [], Type.get('Int'), func)
        yield cls(Load(Name("f"), Type.FUNC), [TEST_INT_LITERAL], Type.get('Int'), func)

    @jit.unroll_safe
    def evaluate(self, frame):
        closure = self.func_node.evaluate(frame)
        assert isinstance(closure, Closure)

        # guard: func
        cached_func = self.cached_func
        jit.promote(cached_func) # immutable
        func = closure.func
        jit.promote(func) # this is most of the point
        if func is not cached_func:
            new_call = GenericCall(self.func_node, self.args, self.type, self.call_count)
            self._replace(new_call)
            return new_call.evaluate_closure(frame, closure.scope, func)

        # TODO inline body?

        return self.evaluate_closure(frame, closure.scope, cached_func)

class GenericCall(Call):
    """A completely generic call"""

    @jit.unroll_safe
    def evaluate(self, frame):
        closure = self.func_node.evaluate(frame)
        assert isinstance(closure, Closure)
        return self.evaluate_closure(frame, closure.scope, closure.func)


class ClosureLoad(Node):
    __slots__ = Node.__slots__ + ['name', 'closure_node']
    _immutable_fields_ = ['name', 'closure_node']

    """For inlining. Extracts a local variable from inside a Closure object."""
    def __init__(self, name, type_, closure_node):
        Node.__init__(self)
        assert isinstance(name, Name)
        self.name = name
        self.type = type_
        assert not closure_node._parent
        closure_node.set_parent(self)
        self.closure_node = closure_node # TODO make this a `name`

        # self.index = index
        # self.depth = depth

    def _copy(self, transform): return ClosureLoad(self.name, self.type, self.closure_node.copy(transform))
    def children(self): return [self.closure_node]

    @classmethod
    def _test_cases(cls):
        yield cls(Name("foo"), Type.get('Int'), Load(Name("func"), Type.FUNC))

    def __repr__(self):
        return "ClosureLoad({!r})".format(self.name)

    @jit.unroll_safe
    def evaluate(self, frame):
        closure_node = self.closure_node
        jit.promote(closure_node) # TODO insert similar jit.promote(self...) everywhere else
        closure = closure_node.evaluate(frame)
        assert isinstance(closure, Closure)
        scope = closure.scope

        name = self.name
        jit.promote(name)
        depth = 0
        while True:
            index = scope.shape.lookup(name)
            if index != -1:
                return scope.lookup(index)
            if not scope.parent:
                raise ValueError(name)
            scope = scope.parent
            depth += 1

        # TODO cache index/depth

    def sexpr(self):
        return self.closure_node.sexpr() + "->" + self.name.sexpr()


# class Apply(Node):
#     def __init__(self, func, arg_list, type_):
#         Node.__init__(self)
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
#         assert isinstance(closure, Closure)
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
    __slots__ = Node.__slots__ + ['child']
    _immutable_fields_ = ['child']

    def __init__(self, child):
        Node.__init__(self)
        self.child = child
        child.set_parent(self)

    def _copy(self, transform): return Return(self.child.copy(transform))
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
    __slots__ = Node.__slots__ + ['symbol', 'record']
    _immutable_fields_ = ['symbol', 'record']

    def __init__(self, symbol, record):
        Node.__init__(self)
        self.symbol = symbol
        self.record = record
        record.set_parent(self)

    def _copy(self, transform): return GetAttr(self.symbol, self.record.copy(transform))
    def children(self): return [self.record]

    def replace_child(self, record, other):
        assert record is self.record
        self.record = other

    def evaluate(self, frame):
        jit.promote(self.record)
        record = self.record.evaluate(frame)
        # TODO fix binary benchmark + inlining
        if not isinstance(record, W_Record):
            print "not a record:", self.record.sexpr()
        assert isinstance(record, W_Record)

        symbol = self.symbol
        jit.promote(symbol)
        shape = record.shape
        jit.promote(shape)
        index = shape.lookup(symbol)
        # TODO cache shape->index, for the interpreter
        return record.values[index]

    def sexpr(self):
        return "(get-attr " + self.record.sexpr() + " " + self.symbol.sexpr() + ")"


class SetAttr(Node):
    __slots__ = Node.__slots__ + ['symbol', 'record', 'value']
    _immutable_fields_ = ['symbol', 'record', 'value']

    def __init__(self, symbol, record, value):
        Node.__init__(self)
        self.symbol = symbol
        self.record = record
        record.set_parent(self)
        self.value = value
        value.set_parent(self)

    def _copy(self, transform): return SetAttr(self.symbol, self.record.copy(transform), self.value.copy(transform))
    def children(self): return [self.record, self.value]

    def replace_child(self, child, other):
        if child is self.record:
            self.record = other
        elif child is self.value:
            self.value = other
        else:
            assert False

    def evaluate(self, frame):
        jit.promote(self.record)
        record = self.record.evaluate(frame)
        assert isinstance(record, W_Record)

        jit.promote(self.value)
        value = self.value.evaluate(frame)

        symbol = self.symbol
        jit.promote(symbol)
        shape = record.shape
        jit.promote(shape)
        index = shape.lookup(symbol)
        # TODO cache shape->index, for the interpreter
        record.values[index] = value

    def sexpr(self):
        return "(set-attr " + self.record.sexpr() + " " + self.symbol.sexpr() + " " + self.value.sexpr() + ")"


#------------------------------------------------------------------------------

class Transform:
    pass

class ReplaceTransform(Transform):
    def __init__(self, replace, with_):
        self.replace = replace
        self.with_ = with_

    def transform(self, node):
        if node == self.replace:
            return self.with_
        return node._copy(self)

class RenameTransform(Transform):
    def __init__(self, replace_names, with_names):
        self.replace = {}
        assert len(replace_names) == len(with_names)
        for i in range(len(replace_names)):
            self.replace[replace_names[i]] = with_names[i]

    def transform(self, node):
        if isinstance(node, Load):
            if node.name in self.replace:
                return Load(self.replace[node.name], node.type)
        elif isinstance(node, Let):
            if node.name in self.replace:
                return Let(self.replace[node.name], node.value.copy(self))
        elif isinstance(node, NewCell):
            if node.name in self.replace:
                return NewCell(self.replace[node.name])
        # TODO Define also
        return node._copy(self)

class ClosureLookupTransform(Transform):
    def __init__(self, closure_node, whitelist, blacklist):
        self.closure_node = closure_node
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.used_closure = False

    def needs_closure_scope(self, name):
        return name in self.blacklist and not name in self.whitelist

    def transform(self, node):
        if isinstance(node, Load):
            if self.needs_closure_scope(node.name):
                self.used_closure = True
                return ClosureLoad(node.name, node.type, self.closure_node.copy())
        return node._copy(self)

