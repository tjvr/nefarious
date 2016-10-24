
from .types import Tree, Type, List, Generic
from .lex import Word

from rpython.rlib.rbigint import rbigint
from rpython.rlib import rope
from rpython.rlib import jit


class Value(Tree):
    def __init__(self, type_, value):
        assert isinstance(desc, str)
        self.type = type_
        self.desc = desc

    def sexpr(self):
        return "<Value>"


class W_Var(Value):
    """a mutable cell"""

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
    def __init__(self, value):
        assert isinstance(value, float)
        self.value = value

    @staticmethod
    @jit.elidable
    def fromstr(string):
        assert isinstance(string, str)
        return W_Float(float(string))

    def __repr__(self):
        return "W_Float({!r})".format(self.value)

    def sexpr(self):
        return str(self.value)


class W_Int(Value):
    type = Type.get('Int')

    def __init__(self, value):
        assert isinstance(value, rbigint)
        self.value = value

    @staticmethod
    @jit.elidable
    def fromstr(string):
        return W_Int(rbigint.fromstr(string))

    @staticmethod
    @jit.elidable
    def fromint(value):
        return W_Int(rbigint.fromint(value))

    @staticmethod
    @jit.elidable
    def fromfloat(value):
        return W_Int(rbigint.fromfloat(value))

    def __repr__(self):
        return 'W_Int({!r})'.format(self.value)

    def sexpr(self):
        return self.value.str()


class W_Text(Value):
    type = Type.get('Text')

    def __init__(self, text):
        assert isinstance(text, rope.StringNode)
        self.text = text

    @staticmethod
    def fromword(word):
        assert isinstance(word, Word)
        string = word.value
        return W_Text(rope.LiteralUnicodeNode(string.decode('utf-8')))
        # TODO tokenizer should understand utf-8

    def __repr__(self):
        return 'W_Text({!r})'.format(self.text)

    def sexpr(self):
        return '"' + self.text.flatten_unicode().encode('utf-8') + '"'

    @staticmethod
    def join(text_list):
        assert isinstance(text_list, W_List)
        l = [t.text for t in text_list.items]
        return W_Text(rope.rebalance(l))

    @staticmethod
    def join_with(text_list, sep):
        return W_Text(rope.join(sep.text, [t.text for t in text_list.items]))

    def split(self):
        # TODO isspace() for unicode ?
        return W_List([W_Text(x) for x in rope.split_chars(self.text,
            predicate=lambda x: unichr(x) == u" ")])

    def split_by(self, sep):
        return W_List([W_Text(x) for x in rope.split(self.text, sep.text)])


class W_List(Value):
    type = List.get(Generic.ALPHA)

    def __init__(self, items):
        assert isinstance(items, list)
        self.items = items

    def __repr__(self):
        return "W_List({})".format(repr(self.items))

    def sexpr(self):
        return "[" + " ".join([c.sexpr() for c in self.items]) + "]"



#------------------------------------------------------------------------------



class Name(Tree):
    """Symbol-like. Compared by identity, not value, so shadowing works."""
    def __init__(self, name):
        assert isinstance(name, str)
        self.name = name # String name really is just a debugging aid
        self._parent = None

    @staticmethod
    def from_word(word):
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
    def get(name):
        assert isinstance(name, str), name
        if name in Symbol._cache:
            symbol = Symbol._cache[name]
        else:
            symbol = Symbol._cache[name] = Symbol(name)
        return symbol

    def __repr__(self):
        return "Symbol({!r})".format(self.name)



#------------------------------------------------------------------------------


class Shape:
    def __init__(self, names, previous=None):
        #assert isinstance(names, dict)
        self.names = names
        self._transitions = {}
        self.previous = previous

    def size(self):
        return len(self.names)

    def lookup(self, key):
        assert isinstance(key, Name)
        return self.names.get(key, -1)

    def transition(self, new_name):
        assert isinstance(new_name, Name), repr(new_name)
        if new_name in self.names:
            raise ValueError("symbol already in record: " + new_name.sexpr())
        if new_name in self._transitions:
            return self._transitions[new_name]
        names = self.names.copy()
        names[new_name] = len(names)
        shape = self._transitions[new_name] = Shape(names, self)
        return shape

    def compatible(self, other):
        shape = self
        while shape.previous:
            shape = shape.previous
            if shape is other:
                return True
        return False

    @staticmethod
    def get(names):
        shape = Shape.EMPTY
        for name in names:
            shape = shape.transition(name)
        return shape

Shape.EMPTY = Shape({})


class W_Record(Value):
    type = Type.get('Record')

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
            shape = self.shape = shape.transition(key)
            assert shape.lookup(key) == len(self.values) # DEBUG
            self.values.append(value)
        else:
            self.values[index] = value

    def _set_shape(self, shape):
        self.shape = shape

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
    def __init__(self, parent, func, values):
        self.parent = parent # from Closure

        assert isinstance(func, Func)
        self.func = func
        self.values = values

        #self.stack = [] # for threading TODO
        #self.calls = [] # for threading

    @property
    def shape(self):
        return self.func.shape

    def set(self, key, value):
        assert isinstance(key, Name)
        shape = self.shape
        index = shape.lookup(key)
        if index == -1:
            shape = shape.transition(key)
            assert shape.lookup(key) == len(self.values) # DEBUG
            self.values.append(value)
            self.func.shape = shape
        else:
            self.values[index] = value

    def lookup(self, key):
        assert isinstance(key, Name)
        index = self.shape.lookup(key)
        if index == -1:
            if self.parent is not None:
                return self.parent.lookup(key)
            raise KeyError(key)
        return self.values[index]

    def _set_shape(self, shape):
        self.shape = self.func.shape = shape
        # TODO also modify other frames on the stack!

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


class Func:
    """a Block plus arg names ??"""
    def __init__(self, arg_names, body):
        #assert isinstance(body, Tree)
        #assert isinstance(body, Block)
        self.body = body

        # map for accessing locals in Frame
        self.shape = Shape.get(arg_names)
        self.arg_length = len(arg_names)

    def sexpr(self):
        return " ".join([n.sexpr() for n in self.shape.names]) + " " + self.body.sexpr()


class W_Func(Value):
    """a Closure: function + scope"""
    type = Type.get('Func')

    def __init__(self, scope, func):
        # for accessing names from outer scopes
        assert isinstance(scope, Frame)
        self.scope = scope

        self.func = func # copy onto closure? TODO opt

    def call(self, arg_list):
        func = self.func
        n = func.arg_length
        assert len(arg_list) == n # TODO dynamic calls
        values = arg_list + [None] * (func.shape.size() - n)

        inner = Frame(self.scope, func, values)
        return inner

    def call_named(self, arg_record):
        pass # TODO allow dynamic calls via Records

    def sexpr(self):
        return "<bound (fun " + self.func.sexpr() + ")>"


class ReturnValue(Exception):
    def __init__(self, value):
        assert isinstance(value, Value)
        self.value = value

