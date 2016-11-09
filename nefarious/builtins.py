from .tree import *



class Builtin(Node):
    type = None

    def __init__(self, args, type_):
        raise NotImplementedError

    def _args(self):
        raise NotImplementedError

    def sexpr(self):
        return "(" + self.__class__.__name__ + " " + " ".join([a.sexpr() for a in self._args()]) + ")"

    def copy(self):
        return self.__class__([a.copy() for a in self._args()], self.type)

    def children(self):
        return self._args()


class UnaryBuiltin(Builtin):
    def __init__(self, args, type_):
        self._parent = None
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
    def __init__(self, args, type_):
        self._parent = None
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
        value = self.child.evaluate(frame)
        print(value.sexpr())


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
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.value + right.value)

class FLOAT_SUB(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.value - right.value)

class FLOAT_MUL(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.value * right.value)

class FLOAT_DIV(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(left.value / right.value)


class FLOAT_LT(InfixBuiltin):
    type = Bool
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Bool.get(left.value < right.value)

class FLOAT_ROUND(UnaryBuiltin):
    type = Int
    arg_types = [Float]
    def evaluate(self, frame):
        f = self.child.evaluate(frame)
        assert isinstance(f, W_Float)
        return W_Int.fromfloat(f.value + 0.5)

class FLOAT_POW(InfixBuiltin):
    type = Float
    arg_types = [Float, Float]
    def evaluate(self, frame):
        left = self.left.evaluate(frame)
        assert isinstance(left, W_Float)
        right = self.right.evaluate(frame)
        assert isinstance(right, W_Float)
        return W_Float(math.pow(left.value, right.value))





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

    def _args(self):
        return [self.cond, self.tv, self.fv]

    # TODO replace_child

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
        self.cond, self.body = values
        self.cond.set_parent(self)
        assert isinstance(self.body, Block)
        self.body.set_parent(self)

    def _args(self):
        return [self.cond, self.body]

    # TODO replace_child

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
