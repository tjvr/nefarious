from .tree import *

def get_while_location(block, cond, self):
    #assert isinstance(self, Node)
    return self.sexpr()

while_driver = jit.JitDriver(
    greens = ['body', 'cond', 'self'],
    reds = ['frame'],
    is_recursive = True,
    get_printable_location = get_while_location,
)


# TODO consider removing assertions, rely on type information instead
# change LoadCell to check the type is as expected!

class Builtin(Node):
    type = None
    __slots__ = Node.__slots__

    def __init__(self, args, type_):
        raise NotImplementedError

    def _args(self):
        raise NotImplementedError

    @classmethod
    def _test_cases(cls):
        values = {
            Type.ANY: W_Text.fromstr("foo"),
            Text: W_Text.fromstr("foo"),
            List.get(Text): W_List([W_Text.fromstr("foo")]),
            List.get(Generic.ALPHA): W_List([W_Int.fromint(i) for i in range(5)]),
            Int: W_Int.fromint(42),
            Float: W_Float(3.142),
            Bool: W_Bool.FALSE,
        }
        yield cls([Literal(values[t], t) for t in cls.arg_types], cls.type)

    def sexpr(self):
        return "(" + self.__class__.__name__ + " " + " ".join([a.sexpr() for a in self._args()]) + ")"

    def _copy(self, transform):
        return self.__class__([a.copy(transform) for a in self._args()], self.type)

    def children(self):
        return self._args()


class UnaryBuiltin(Builtin):
    __slots__ = Node.__slots__ + ['child']
    _immutable_fields_ = ['child']

    def __init__(self, args, type_):
        Node.__init__(self)
        self.child, = args
        self.child.set_parent(self)
    def _args(self):
        return [self.child]
    def replace_child(self, child, other):
        if child is self.child:
            self.child = other
        else:
            assert False


class InfixBuiltin(Builtin):
    __slots__ = Node.__slots__ + ['left', 'right']
    _immutable_fields_ = ['left', 'right']

    def __init__(self, args, type_):
        Node.__init__(self)
        self.left, self.right = args
        self.left.set_parent(self)
        self.right.set_parent(self)
    def _args(self):
        return [self.left, self.right]
    def replace_child(self, child, other):
        if child is self.left:
            self.left = other
        elif child is self.right:
            self.right = other
        else:
            assert False


class PRINT(UnaryBuiltin):
    type = Internal.get('Line')
    arg_types = [Type.ANY]
    def evaluate(self, frame):
        jit.promote(self.child)
        value = self.child.evaluate(frame)
        print(value.sexpr()) # PRINT

class REPR(UnaryBuiltin):
    type = Type.get('Text')
    arg_types = [Type.ANY]
    def evaluate(self, frame):
        jit.promote(self.child)
        value = self.child.evaluate(frame)
        return W_Text.fromstr(value.sexpr()) # REPR


Bool = Type.get('Bool')

class BOOL_NOT(UnaryBuiltin):
    type = Bool
    arg_types = [Bool]
    def evaluate(self, frame):
        jit.promote(self.child)
        child = self.child.evaluate(frame)
        assert isinstance(child, W_Bool)
        return W_Bool.get(not child.prim)

class BOOL_OR(InfixBuiltin):
    type = Bool
    arg_types = [Bool, Bool]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Bool)
        if left.prim:
            return Value.TRUE
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Bool)
        if right.prim:
            return Value.TRUE
        return Value.FALSE

class BOOL_AND(InfixBuiltin):
    type = Bool
    arg_types = [Bool, Bool]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Bool)
        if not left.prim:
            return Value.FALSE
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Bool)
        if not right.prim:
            return Value.FALSE
        return Value.TRUE

class IS_NIL(UnaryBuiltin):
    type = Bool
    arg_types = [Type.ANY]
    def evaluate(self, frame):
        child = self.child
        jit.promote(child)
        value = child.evaluate(frame)
        return W_Bool.get(value == Value.NULL)


Int = Type.get('Int')

class INT_ADD(InfixBuiltin):
    type = Int
    arg_types = [Int, Int]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Int(left.prim.add(right.prim))

class INT_SUB(InfixBuiltin):
    type = Int
    arg_types = [Int, Int]
    def evaluate(self, frame): # this is expensive
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Int(left.prim.sub(right.prim))

class INT_MUL(InfixBuiltin):
    type = Int
    arg_types = [Int, Int]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Int(left.prim.mul(right.prim))

class INT_EQ(InfixBuiltin):
    type = Bool
    arg_types = [Int, Int]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Bool.get(left.prim.eq(right.prim))

class INT_LT(InfixBuiltin):
    type = Bool
    arg_types = [Int, Int]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        return W_Bool.get(left.prim.lt(right.prim))

class INT_RANDOM(InfixBuiltin):
    type = Int
    arg_types = [Int, Int]

    random = Random(seed=int(time.time()))

    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Int)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Int)
        # TODO random for bigints.
        start = left.prim.toint()
        end = right.prim.toint()
        f = INT_RANDOM.random.random()
        value = int(0.5 + start + f * (end - start))
        return W_Int.fromint(value)

class INT_FLOAT(UnaryBuiltin):
    type = Type.get('Float')
    arg_types = [Int]
    def evaluate(self, frame):
        jit.promote(self.child)
        child = self.child.evaluate(frame)
        assert isinstance(child, W_Int)
        return W_Float(child.prim.tofloat())



Float = Type.get('Float')

class FLOAT_ADD(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.prim + right.prim)

class FLOAT_SUB(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.prim - right.prim)

class FLOAT_MUL(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.prim * right.prim)

class FLOAT_DIV(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.prim / right.prim)


class FLOAT_LT(InfixBuiltin):
    type = Bool
    arg_types = [Float, Float]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Bool.get(left.prim < right.prim)

class FLOAT_ROUND(UnaryBuiltin):
    type = Int
    arg_types = [Float]
    def evaluate(self, frame):
        jit.promote(self.child)
        f = self.child.evaluate(frame)
        assert isinstance(f, W_Float)
        return W_Int.fromfloat(f.prim + 0.5)

class FLOAT_POW(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(math.pow(left.prim, right.prim))





Text = Type.get('Text')

class TEXT_JOIN(UnaryBuiltin):
    type = Text
    arg_types = [List.get(Text)]
    def evaluate(self, frame):
        jit.promote(self.child)
        text_list = self.child.evaluate(frame)
        return W_Text.join(text_list)

class TEXT_SPLIT(UnaryBuiltin):
    type = List.get(Text)
    arg_types = [Text]
    def evaluate(self, frame):
        jit.promote(self.child)
        text = self.child.evaluate(frame)
        return text.split()

class TEXT_JOIN_WITH(InfixBuiltin):
    type = Text
    arg_types = [List.get(Text), Text]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        left = self.left.evaluate(frame)
        right = self.right.evaluate(frame)
        return W_Text.join_with(left, right)

class TEXT_SPLIT_BY(InfixBuiltin):
    type = List.get(Text)
    arg_types = [Text, Text]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
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
    __slots__ = Node.__slots__ + ['cond', 'tv', 'fv']
    _immutable_fields_ = ['cond', 'tv', 'fv']

    def __init__(self, values, type_):
        Node.__init__(self)
        self.cond, self.tv, self.fv = values
        self.cond.set_parent(self)
        self.tv.set_parent(self)
        self.fv.set_parent(self)

    def _args(self):
        return [self.cond, self.tv, self.fv]

    @classmethod
    def _test_cases(cls):
        return [] # TODO test IF

    def replace_child(self, child, other):
        if child is self.cond:
            self.cond = other
        elif child is self.tv:
            self.tv = other
        elif child is self.fv:
            self.fv = other
        else:
            assert False

    def sexpr(self):
        return "(IF_THEN_ELSE " + self.cond.sexpr() + " " + self.tv.sexpr() + " " + self.fv.sexpr() + ")"

    def evaluate(self, frame): # TODO OPT
        cond = self.cond.evaluate(frame)
        assert isinstance(cond, W_Bool)
        if cond.prim:
            return self.tv.evaluate(frame)
        else:
            return self.fv.evaluate(frame)


class IF_THEN(Builtin):
    type = _Line
    arg_types = [Bool, _Block]
    __slots__ = Node.__slots__ + ['cond', 'body']
    _immutable_fields_ = ['cond', 'body']

    def __init__(self, values, type_):
        Node.__init__(self)
        self.cond, self.body = values
        self.cond.set_parent(self)
        self.body.set_parent(self)

    def _args(self):
        return [self.cond, self.body]

    @classmethod
    def _test_cases(cls):
        return [] # TODO test IF

    def replace_child(self, child, other):
        if child is self.cond:
            self.cond = other
        elif child is self.body:
            self.body = other
        else:
            assert False

    def sexpr(self):
        return "(IF_THEN " + self.cond.sexpr() + " " + self.body.sexpr() + ")"

    def evaluate(self, frame): # TODO OPT
        cond = self.cond
        jit.promote(cond)
        cond = cond.evaluate(frame)
        assert isinstance(cond, W_Bool)
        if cond.prim:
            body = self.body
            jit.promote(body)
            body.evaluate(frame)


class WHILE(Builtin):
    type = _Line
    arg_types = [Bool, _Block]
    __slots__ = Node.__slots__ + ['cond', 'body']
    _immutable_fields_ = ['cond', 'body']

    def __init__(self, values, type_):
        Node.__init__(self)
        self.cond, self.body = values
        assert isinstance(self.cond, Node)
        self.cond.set_parent(self)
        self.body.set_parent(self)

    def _args(self):
        return [self.cond, self.body]

    @classmethod
    def _test_cases(cls):
        return [] # TODO test WHILE
        #yield WHILE([Literal(W_Bool.TRUE, Bool), Block], _Line)

    def replace_child(self, child, other):
        if child is self.cond:
            self.cond = child
        elif child is self.body:
            self.body = other

    def sexpr(self):
        return "(WHILE " + self.cond.sexpr() + " " + self.body.sexpr() + ")"

    def evaluate(self, frame):
        cond, body = self.cond, self.body
        jit.promote(cond)
        jit.promote(body)

        while True:
            carry_on = cond.evaluate(frame)
            jit.promote(carry_on)
            assert isinstance(carry_on, W_Bool)
            if not carry_on.prim:
                break
            while_driver.jit_merge_point(self=self, cond=cond, body=body, frame=frame)
            body.evaluate(frame)


_List = List.get(_a)

class LIST_ADD(InfixBuiltin):
    type = _Line
    arg_types = [_List.get(_a), _a]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        list_ = self.left.evaluate(frame)
        item = self.right.evaluate(frame)
        assert isinstance(list_, W_List)
        list_.items().append(item)

    @classmethod
    def _test_cases(cls):
        # TODO test LIST_ADD
        return []

class LIST_GET(InfixBuiltin):
    type = _a
    arg_types = [_List.get(_a), Int]
    def evaluate(self, frame):
        jit.promote(self.left)
        jit.promote(self.right)
        list_ = self.left.evaluate(frame)
        assert isinstance(list_, W_List)
        int_ = self.right.evaluate(frame)
        assert isinstance(int_, W_Int)
        index = int_.prim.toint()
        if not 1 <= index <= len(list_.items()):
            raise IndexError(index) # TODO error handling
        return list_.items()[index - 1]

class LIST_LEN(UnaryBuiltin):
    type = Int
    arg_types = [_List.get(_a)]
    def evaluate(self, frame):
        jit.promote(self.child)
        list_ = self.child.evaluate(frame)
        assert isinstance(list_, W_List)
        return W_Int.fromint(len(list_.items()))

