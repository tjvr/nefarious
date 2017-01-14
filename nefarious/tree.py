
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
    reds = ['arguments', 'func', 'scope', 'frame'],
    is_recursive = True,
    get_printable_location = get_location,
    should_unroll_one_iteration = lambda self: True, # may or may not be necessary?
)


#------------------------------------------------------------------------------

from .types import *
from .values import *

# TODO annotate nodes with SourceSections

class Sequence(Node):
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
        yield Sequence([Literal._TEST_INT])

    def replace_child(self, child, other):
        for index in range(len(self.nodes)):
            if self.nodes[index] is child:
                self.nodes[index] = other
                return
        assert False

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
        #print '\/', self.sexpr()
        jit.promote(self.nodes) # assume replace_child won't happen in traced code
        for node in self.nodes:
            #print '>>', node.sexpr()
            value = node.evaluate(frame)
        return value


class Literal(Node):
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
        yield cls._TEST_INT

    def __repr__(self):
        return "Literal({!r})".format(self.value)

    def sexpr(self):
        return self.value.sexpr()

    def evaluate(self, frame):
        return self.value

Literal._TEST_INT = Literal(W_Int.fromint(42), Type.get('Int'))

class ListLiteral(Node):
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
        yield cls([Literal._TEST_INT], List.get(Type.get('Int')))

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
    type = Type.get('Record')
    def __init__(self, keys, values, type_):
        Node.__init__(self)
        self.keys = keys
        self.values = values
        self.type = type_
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
    def __init__(self, name, type_):
        Node.__init__(self)
        assert isinstance(name, Name)
        self.name = name
        self.type = type_
        self.index = -1
        self.depth = -1

    def compile(self, stack):
        # TODO assert self._parent
        assert self._parent
        #assert self.index == -1, self._parents
        for depth in range(len(stack)):
            shape = stack[len(stack) - depth - 1]
            index = shape.lookup(self.name)
            if index != -1:
                #if self.index != -1:
                #    assert self.index == index
                self.index = index
                self.depth = depth
                break
        else:
            raise ValueError(self.name)
        self.s = list(stack)

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
        assert frame # TODO help

        index = self.index
        jit.promote(index)
        return frame.lookup(index)

    def sexpr(self):
        return self.name.sexpr()


class Let(Node):
    """For let-bindings"""
    def __init__(self, name, value):
        Node.__init__(self)
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

    def _copy(self, transform): return Let(self.name, self.value.copy(transform))
    def children(self): return [self.value]

    @classmethod
    def _test_cases(cls):
        yield cls(Name("quxx"), Literal._TEST_INT)

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

    def __init__(self, name):
        Node.__init__(self)
        self.name = name
        self.index = -1

    def compile(self, stack):
        #assert self.index == -1
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

        # DEBUG
        assert self.index == frame.shape.lookup(self.name)

        index = self.index
        jit.promote(index)
        cell = W_Var(Value.NULL)
        frame.set(index, cell)
        return cell


class LoadCell(Node):
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
        yield cls(Load(Name("x"), Type.VAR), Literal._TEST_INT)

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


class Define(Node):
    """A little like `let rec` I suppose"""
    def __init__(self, name, func):
        Node.__init__(self)
        assert isinstance(name, Name)
        self.name = name
        #func.body.set_parent(self) # TODO: this is questionable
        self.func = func
        self.index = -1

    def _copy(self, transform): return Define(self.name, FuncDef(self.func.shape.names_list(), self.func.body.copy(transform)))
    def children(self): return [self.func.body]

    @classmethod
    def _test_cases(cls):
        yield cls(Name("f"), FuncDef([], Sequence([Literal._TEST_INT])))

    def compile(self, stack):
        shape = stack.pop()
        self.index, shape = shape.lookup_or_insert(self.name)
        stack.append(shape)

        shape = self.func.shape
        stack.append(shape)
        self.func.body.compile(stack)
        self.func.shape = stack.pop()

    def evaluate(self, frame):
        closure = Closure(frame, self.func)
        index = self.index
        jit.promote(index)
        frame.set(index, closure)
        return None

    def sexpr(self):
        return "(define " + self.name.sexpr() + " " + self.func.sexpr() + ")"


class Lambda(Node):
    type = Type.FUNC

    def __init__(self, func):
        Node.__init__(self)
        assert isinstance(func, FuncDef)
        self.func = func

    def compile(self, stack):
        shape = self.func.shape
        stack.append(shape)
        self.func.body.compile(stack)
        self.func.shape = stack.pop()

    # The interaction between Lambda and FuncDef is unpleasant.
    #def _copy(self, transform): return Lambda(self.func)
    def _copy(self, transform): return Lambda(FuncDef(self.func.arg_names(), self.func.body.copy(transform)))
    #def _copy(self, transform): return Lambda(FuncDef(self.func.shape.names_list(), self.func.body.copy(transform)))
    def children(self): return [self.func.body]

    @classmethod
    def _test_cases(cls):
        yield cls(FuncDef([], Sequence([Literal._TEST_INT])))

    def evaluate(self, frame):
        jit.promote(self.func)
        closure = Closure(frame, self.func)
        return closure

    def sexpr(self):
        return "(fun " + self.func.sexpr() + ")"


class Call(Node):
    def __init__(self, func_node, args, type_, call_count=0):
        Node.__init__(self)
        assert isinstance(func_node, Node)
        #assert func_node.type == Type.FUNC
        self.func_node = func_node
        self.args = args
        self.type = type_
        func_node.set_parent(self)
        # nb. does this require jit.unroll_safe ?
        for arg in args:
            assert isinstance(arg, Node)
            arg.set_parent(self)
        self.call_count = call_count
        self.cached_func = None
        self.cached_closure = None

    @classmethod
    def _test_cases(cls):
        yield cls(Load(Name("f"), Type.FUNC), [], Type.get('Int'))
        yield cls(Load(Name("f"), Type.FUNC), [Literal._TEST_INT], Type.get('Int'))

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

    @jit.unroll_safe
    def evaluate(self, frame):
        func_node = self.func_node
        closure = func_node.evaluate(frame)
        assert isinstance(closure, Closure)
        func = closure.func
        self.cached_closure = closure
        #print "Call", self.func_node.sexpr(), "; shape", func.shape.names_list()

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
            #print "transition", new_call.__class__.__name__
            self._replace(new_call)
            return new_call.evaluate_closure(frame, closure.scope, func)

        self.cached_closure = closure
        return self.evaluate_closure(frame, closure.scope, closure.func)

    @jit.unroll_safe
    def evaluate_closure(self, frame, scope, func):
        assert len(self.args) == func.arg_length
        arguments = [arg.evaluate(frame) for arg in self.args]
        return self.evaluate_arguments(arguments, scope, func)

    @jit.unroll_safe
    def evaluate_arguments(self, arguments, scope, func):
        #print "Func", id(func)(
        make_sure_not_resized(arguments)
        self.call_count += 1

        frame = Frame(scope, func.shape, func)
        for index, value in enumerate(arguments):
            frame.set(index, value)

        call_driver.jit_merge_point(self=self, frame=frame, scope=scope, func=func, arguments=arguments)

        body = func.body # no longer immutable...
        jit.promote(body)
        try:
            result = body.evaluate(frame)
        except ReturnValue as ret: # TODO opt
            result = ret.value
        return result


class StaticCall(Call):
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
        # yield cls(Load(Name("f"), Type.FUNC), [Literal._TEST_INT], Type.get('Int'), closure)

    @jit.unroll_safe
    def evaluate(self, frame):
        func_node = self.func_node
        jit.promote(func_node) # nb. this could of course change
        closure = func_node.evaluate(frame)
        assert isinstance(closure, Closure)
        #print "StaticCall", self.func_node.sexpr(), "; shape", closure.func.shape.names_list()

        # guard: closure
        cached_closure = self.cached_closure
        jit.promote(cached_closure) # immutable
        jit.promote(closure)
        if closure is not cached_closure: # guard
            if closure.func is cached_closure.func:
                new_call = FuncCall(self.func_node, self.args, self.type, closure.func, self.call_count)
            else:
                new_call = GenericCall(self.func_node, self.args, self.type, self.call_count)
            #print "transition", new_call.__class__.__name__
            self._replace(new_call)
            return new_call.evaluate_closure(frame, closure.scope, closure.func)

        # inlining
        if self.call_count == 3: # 4th call
            # can't inline into global scope.
            if frame.func:
                #print('inlining: ' + str(closure.func.body.weight))
                self.inline_call(frame.func, frame, closure)
            # takes effect on next call to `outer_func`.
            # TODO rewrite immediately and modify Frames on stack?

            # nb. if the next call is recursive, it'll use the new `outer_func`
            # body.

        return self.evaluate_closure(frame, closure.scope, closure.func)

    def inline_arguments(self, closure_locals):
        args = self.args
        names = closure_locals[:len(args)]
        return [Let(names[i], args[i].copy()) for i in range(len(args))]

    def inline_body(self, closure, closure_args, outer_scope):
        if isinstance(self.func_node, Load):
            closure_name = self.func_node.name
        else:
            closure_name = Name("closure")
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
        # Move argument evaluation into `Let`s
        closure_locals = closure.func.shape.names_list()
        items = self.inline_arguments(closure_locals)

        # Copy body & replace closure-scope lookups.
        closure_args = closure_locals[:len(self.args)]
        closure_node, body = self.inline_body(closure, closure_args, frame)
        items.append(body)

        # avoid evaluating func_node twice.
        func_node = self.func_node.copy()
        let = None
        if closure_node:
            if isinstance(self.func_node, Load) and self.func_node.name == closure_node.name:
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
        #print inlined.sexpr()

        # Rewrite outer_func
        transform = ReplaceTransform(replace=self, with_=inlined)
        outer_func.body = outer_func.body.copy(transform)

        # Fix outer_func's Frame shape.
        stack = frame.shape_stack()
        #stack.append(outer_func.shape)
        #assert stack[-1] == stack[-2]
        outer_func.body.compile(stack)
        #assert len(outer_func.shape.names_list()) <= stack[-1].names_list()
        outer_func.shape = stack.pop()

        #print "rewrote", outer_func, "; shape", outer_func.shape.names_list()
        b = outer_func.body
        if b._parent: b = b._parent
        #print b.sexpr()

    @jit.dont_look_inside
    def _inline(self, defn, scope, closure):
        func = closure.func
        # we can't mutate the tree *right now*, because we're in the middle
        # of evaluating this Frame! won't have space for variables...
        #print self.sexpr()
        arg_nodes = self.args
        local_names = func.shape.names_list()
        arg_names = local_names[:len(arg_nodes)]
        items = []
        for i in range(len(arg_nodes)):
            name = local_names[i]
            value_node = arg_nodes[i]
            items.append(Let(name, value_node.copy()))

        name = Name("closure")
        items.append(Let(name, self.func_node.copy()))
        closure_node = Load(name, Type.FUNC)

        whitelist = scope.all_names()
        blacklist = closure.scope.all_names()
        for name in local_names:
            whitelist[name] = True
        transform = ClosureLookupTransform(closure_node, whitelist, blacklist)
        body = func.original_body.copy(transform)
        items.append(body)

        # TODO insert deopt node

        body = Sequence(items)
        inlined = InlinedStatic(self.func_node.copy(), self.args, self.type, closure, body, self.call_count)
        #print inlined.sexpr()
        transform = ReplaceTransform(replace=self, with_=inlined)
        new_body = defn.body.copy(transform)

        stack = [defn.shape, scope.shape]
        while scope.parent:
            scope = scope.parent
            stack.append(scope.shape)
        stack.reverse()
        new_body.compile(stack) # set up new Shape.
        defn.shape = stack.pop()
        defn.body = new_body

        #print "rewrote", id(scope.func), "; shape", defn.shape.names_list()
        #print new_body.sexpr()


class InlinedStatic(StaticCall):
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

        #print "eval inline", self.func_node.sexpr()

        # guard: closure
        cached_closure = self.cached_closure
        jit.promote(cached_closure) # immutable
        jit.promote(closure)
        if closure is not cached_closure: # guard
            #print 'inline deopt'
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
        assert isinstance(func, FuncDef)
        self.cached_func = func

    @classmethod
    def _test_cases(cls):
        func = FuncDef([], Sequence([Literal._TEST_INT]))
        yield cls(Load(Name("f"), Type.FUNC), [], Type.get('Int'), func)
        yield cls(Load(Name("f"), Type.FUNC), [Literal._TEST_INT], Type.get('Int'), func)

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

        #print "FuncCall", self.func_node.sexpr(), "; shape", func.shape.names_list()
        # TODO inline body?

        return self.evaluate_closure(frame, closure.scope, cached_func)

class GenericCall(Call):
    """A completely generic call"""

    @jit.unroll_safe
    def evaluate(self, frame):
        #print "GenericCall", self.func_node.sexpr()
        #print self.func_node
        #print self.func_node.__class__
        #, "; shape", closure.func.shape.names_list()
        closure = self.func_node.evaluate(frame)
        assert isinstance(closure, Closure)
        return self.evaluate_closure(frame, closure.scope, closure.func)


class ClosureLoad(Node):
    """For inlining. Extracts a local variable from inside a Closure object."""
    def __init__(self, name, type_, closure_node):
        Node.__init__(self)
        assert isinstance(name, Name)
        self.name = name
        self.type = type_
        assert not closure_node._parent
        closure_node.set_parent(self)
        self.closure_node = closure_node

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
        shape = self.shape
        jit.promote(shape)
        if record.shape is not shape:
            other = GetAttrGeneric(self.symbol, self.record)
            # TODO rewrite
            return other.evaluate_record(record)

        index = self.index
        jit.promote(index)
        return record.values[index]

class GetAttrGeneric(GetAttr):
    def evaluate_record(self, record):
        symbol = self.symbol
        jit.promote(symbol)
        return record.lookup(symbol)


class SetAttr(Node):
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
        shape = self.shape
        jit.promote(shape)
        if record.shape is not shape:
            other = SetAttrGeneric(self.symbol, self.record, self.value)
            # TODO rewrite
            return other.evaluate_record(record, value)

        index = self.index
        jit.promote(index)
        record.values[index] = value

class SetAttrGeneric(SetAttr):
    def evaluate_record(self, record, value):
        symbol = self.symbol
        jit.promote(symbol)
        record.set(symbol, value)


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

class ClosureLookupTransform(Transform):
    def __init__(self, closure_node, whitelist, blacklist):
        self.closure_node = closure_node
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.used_closure = False

    def needs_closure_scope(self, name):
        return name in self.blacklist and not name in self.whitelist

    def transform(self, node):
        out = node._copy(self)
        assert out is not node
        if isinstance(node, Load):
            if self.needs_closure_scope(node.name):
                out = ClosureLoad(node.name, node.type, self.closure_node.copy())
                self.used_closure = True
            #print node.sexpr(), '->', out.sexpr()
        return out

