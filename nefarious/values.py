
from .types import Type, List, Generic

try:
    from rpython.rlib.rbigint import rbigint
    from rpython.rlib import rope
    from rpython.rlib import jit
    from rpython.rlib.debug import make_sure_not_resized
except ImportError:
    # TODO can we write cpython stubs for these? or is that too much work?
    raise ImportError("Please run `make pypy`")


class Value:
    __slots__ = ['type', 'prim']
    _immutable_fields_ = ['type', 'prim']

    def __init__(self, type_, value):
        assert isinstance(desc, str)
        self.type = type_
        self.desc = desc

    def sexpr(self):
        return "<Value>"


class W_Var(Value):
    """a mutable cell"""
    # TODO can this be virtualized?

    def __init__(self, value):
        self.value = value

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
    @jit.elidable
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
    # TODO type ??
    def __init__(self): pass
    def __repr__(self): return 'Value.NULL'
    def sexpr(self): return 'null'
Value.NULL = W_Null()


class W_Float(Value):
    type = Type.get('Float')

    def __init__(self, prim):
        assert isinstance(prim, float)
        self.prim = prim

    @staticmethod
    @jit.elidable
    def fromstr(string):
        assert isinstance(string, str)
        return W_Float(float(string))

    def __repr__(self):
        return "W_Float({!r})".format(self.prim)

    def sexpr(self):
        return str(self.prim)


class W_Int(Value):
    type = Type.get('Int')
    _immutable_fields_ = ['value']

    def __init__(self, prim):
        assert isinstance(prim, rbigint)
        self.prim = prim

    @staticmethod
    @jit.elidable
    def fromstr(string):
        return W_Int(rbigint.fromstr(string))

    @staticmethod
    @jit.elidable
    def fromint(prim):
        return W_Int(rbigint.fromint(prim))

    @staticmethod
    @jit.elidable
    def fromfloat(prim):
        return W_Int(rbigint.fromfloat(prim))

    def __repr__(self):
        return 'W_Int({!r})'.format(self.prim)

    def sexpr(self):
        return self.prim.str()


class W_Text(Value):
    type = Type.get('Text')
    _immutable_fields_ = ['value']

    def __init__(self, prim):
        assert isinstance(prim, rope.StringNode)
        self.prim = prim

    @staticmethod
    @jit.elidable
    def fromstr(string):
        # TODO tokenizer should understand utf-8
        return W_Text(rope.LiteralUnicodeNode(string.decode('utf-8')))

    @jit.elidable
    def _rope(self):
        return self.prim

    def __repr__(self):
        return 'W_Text({!r})'.format(self.prim)

    def sexpr(self):
        return '"' + self.prim.flatten_unicode().encode('utf-8') + '"'

    @staticmethod
    def join(text_list):
        assert isinstance(text_list, W_List)
        l = [t._rope() for t in text_list.items()]
        return W_Text(rope.rebalance(l))

    @staticmethod
    def join_with(text_list, sep):
        return W_Text(rope.join(sep._rope(), [t._rope() for t in text_list.items()]))

    def split(self):
        # TODO isspace() for unicode ?
        return W_List([W_Text(x) for x in rope.split_chars(self.prim,
            predicate=lambda x: unichr(x) == u" ")])

    def split_by(self, sep):
        return W_List([W_Text(x) for x in rope.split(self.prim, sep._rope())])


class W_List(Value):
    type = List.get(Generic.ALPHA)

    def __init__(self, items):
        assert isinstance(items, list)
        self.prim = items

    @jit.elidable
    def items(self):
        assert isinstance(self.prim, list)
        return self.prim

    def __repr__(self):
        return "W_List({})".format(repr(self.prim))

    def sexpr(self):
        return "[" + " ".join([c.sexpr() for c in self.prim]) + "]"


class W_Type(Value):
    type = Type.TYPE
    def __init__(self, type_):
        self.prim = type_

    def __repr__(self):
        return "W_Type({})".format(repr(self.prim))

    def sexpr(self):
        return "<" + self.prim._str() + ">"


#------------------------------------------------------------------------------


class Name:
    _immutable_fields_ = ['name']

    """Symbol-like. Compared by identity, not value, so shadowing works."""
    _immutable_fields_ = ['name']
    #__slots__ = ['name']

    def __init__(self, name):
        assert isinstance(name, str)
        self.name = name # String name really is just a debugging aid

    @staticmethod
    def from_word(word):
        from .lex import Word
        assert isinstance(word, Word)
        return Name(word.value)

    def __repr__(self):
        return "Name({!r})".format(self.name)

    def sexpr(self):
        return self.name.replace(" ", "_")


class Symbol(Name):
    """Name, specialised for let-bindings & arguments."""
    _cache = {}

    @staticmethod
    @jit.elidable
    def get(name):
        assert isinstance(name, str), name
        if name in Symbol._cache:
            symbol = Symbol._cache[name]
        else:
            symbol = Symbol._cache[name] = Symbol(name)
        return symbol

    def __repr__(self):
        return "Symbol({!r})".format(self.name)

    def sexpr(self):
        return ":" + self.name.replace(" ", "_")



#------------------------------------------------------------------------------


class Shape:
    _immutable_fields_ = ['names', 'previous']

    def __init__(self, names, previous=None):
        #assert isinstance(names, dict)
        self.names = names
        self._transitions = {}
        self.previous = previous

    @jit.elidable
    def size(self):
        return len(self.names)

    @jit.elidable
    def lookup(self, key):
        assert isinstance(key, Name)
        return self.names.get(key, -1)

    @jit.elidable
    def insert(self, new_name):
        assert isinstance(new_name, Name)
        if new_name in self.names:
            raise ValueError("symbol already in record: " + new_name.sexpr())
        if new_name in self._transitions:
            return self._transitions[new_name]
        names = self.names.copy()
        names[new_name] = len(names)
        shape = self._transitions[new_name] = Shape(names, self)
        return shape

    @jit.elidable
    def lookup_or_insert(self, new_name):
        if new_name in self.names:
            shape = self
        else:
            shape = self.insert(new_name)
        index = shape.lookup(new_name)
        return index, shape

    @jit.elidable
    def compatible(self, other):
        # TODO opt?
        shape = self
        while shape.previous:
            shape = shape.previous
            if shape is other:
                return True
        return False

    @jit.elidable
    def names_list(self):
        result = [None] * len(self.names)
        for name, index in self.names.items():
            result[index] = name
        return result

    @staticmethod
    @jit.elidable
    def get(names):
        shape = Shape.EMPTY
        for name in names:
            shape = shape.insert(name)
        return shape

Shape.EMPTY = Shape({})


class W_Record(Value):
    type = Type.get('Record')
    __slots__ = ['shape', 'values']

    # TODO should records be immutable?

    def __init__(self, keys, values):
        self.shape = Shape.get(keys)
        self.values = values
        assert len(keys) == len(values)
        # first,second,third TODO opt

    def set(self, key, value):
        assert isinstance(key, Symbol)
        shape = self.shape
        index = shape.lookup(key)
        if index == -1:
            shape = self.shape = shape.insert(key)
            assert shape.lookup(key) == len(self.values) # DEBUG
            self.values.append(value)
        else:
            self.values[index] = value

    def lookup(self, key):
        assert isinstance(key, Symbol)
        index = self.shape.lookup(key)
        if index == -1:
            raise KeyError(key)
        return self.values[index]

    def sexpr(self):
        values = self.values
        symbols = []
        lookup = self.shape.names
        for index in range(len(values)):
            for key in lookup:
                if lookup[key] == index:
                    symbols.append(key)
        return "[" + " ".join([
            ":" + symbols[i].name + " " + values[i].sexpr()
            for i in range(len(symbols))
        ]) + "]"


class Frame:
    _virtualizable_ = ['values[*]']
    _immutable_fields_ = ['parent', 'shape']

    def __init__(self, parent, shape):
        self = jit.hint(self, access_directly=True, fresh_virtualizable=True)

        self.parent = parent # from Closure
        assert isinstance(shape, Shape)
        self.shape = shape

        values = [None] * shape.size()
        make_sure_not_resized(values)
        self._values = values

        #self.stack = [] # for threading TODO
        #self.calls = [] # for threading

    def set_offset(self, index, value):
        # Can assign each slot exactly once.
        jit.promote(index)
        values = self._values
        assert 0 <= index < len(values)
        values[index] = value

    def lookup_offset(self, index):
        jit.promote(index)
        values = self._values
        assert 0 <= index < len(values)
        return values[index]

    # TODO use jit.hint(frame, force_virtualizable=True) for closure escape

    def _print(self):
        values = self.values
        symbols = []
        lookup = self.shape.names
        for index in range(len(values)):
            for key in lookup:
                if lookup[key] == index:
                    symbols.append(key)
        print "<Frame [" + " ".join([
            ":" + symbols[i].name + " " + ("None" if values[i] is None else values[i].sexpr())
            for i in range(len(symbols))
        ]) + "]"


class Func: # TODO naming
    """a Block plus arg names ??"""
    _immutable_fields_ = ['original_body', 'shape', 'arg_length']

    def __init__(self, arg_names, body):
        #assert isinstance(body, Tree)
        #assert isinstance(body, Block)
        self.body = body
        self.original_body = None if body is None else body.copy()

        # map for accessing locals in Frame
        self.shape = Shape.get(arg_names)
        self.arg_length = len(arg_names)

    def sexpr(self):
        return " ".join([n.sexpr() for n in self.shape.names]) + " " + self.body.sexpr()


class W_Func(Value): # TODO naming
    """a Closure: function + scope"""
    type = Type.get('Func')
    __slots__ = ['scope', 'func']
    _immutable_fields_ = ['scope', 'func']

    def __init__(self, scope, func):
        # for accessing names from outer scopes
        assert isinstance(scope, Frame)
        self.scope = scope

        self.func = func

    def sexpr(self):
        return "<bound (fun " + self.func.sexpr() + ")>"


class ReturnValue(Exception):
    def __init__(self, value):
        assert isinstance(value, Value)
        self.value = value

