
from .types import Tree, Type


class Value(Tree):
    def __init__(self, type_, value):
        assert isinstance(desc, str)
        self.type = type_
        self.desc = desc

    def sexpr(self):
        return "<Value>"


class W_Var(Value):
    """a mutable cell"""

    def __init__(self):
        self.value = None
        self.set(Value.NULL)

    def __repr__(self):
        return "<W_Var {}>".format(hex(id(self))[-6:-2])

    def get(self):
        assert isinstance(self.value, Value)
        return self.value

    def set(self, value):
        assert isinstance(value, Value)
        self.value = value

    def sexpr(self):
        return "<Var>"


class W_Bool(Value):
    type = Type.get('Bool')
    def __init__(self):
        assert False

    def __repr__(self):
        return 'W_Bool({})'.format(self.sexpr())

    @staticmethod
    def get(value):
        return W_Bool.TRUE if value else W_Bool.FALSE

class W_True(W_Bool):
    value = True
    def __init__(self): pass
    def sexpr(self): return 'yes'

class W_False(W_Bool):
    value = False
    def __init__(self): pass
    def sexpr(self): return 'no'

Value.TRUE = W_True()
Value.FALSE = W_False()


# TODO ditch in favour of Options
class W_Null(Value):
    def __init__(self): pass
    def __repr__(self): return 'Value.NULL'
    def sexpr(self): return 'null'
Value.NULL = W_Null()


class W_Int(Value):
    type = Type.get('Int')
    def __init__(self, value):
        assert isinstance(value, int)
        self.value = value

    def __repr__(self):
        return 'W_Int({})'.format(str(self.value))

    def sexpr(self):
        return str(self.value)


# Decimal

#grammar.add(Int, [Word.DIGITS, Word.word("."), Word.DIGITS], ParseDecimal)
# TODO W_Decimal


# TODO W_Text (using ropes!)

