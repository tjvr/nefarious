
class Tree:
    def sexpr(self):
        raise NotImplementedError


class Tag(Tree):
    def specialise(self, unification):
        return self

    def is_super(self, other):
        if self is other:
            return Unification()

class Type(Tag):
    """A non-terminal / type name."""
    _cache = {}

    def __init__(self, name):
        self.name = name
        self._union = {}
        self.has_generic = False

    def __repr__(self):
        return 'Type({!r})'.format(self.name)

    def __str__(self):
        return self._str()

    def _str(self):
        return self.name

    @staticmethod
    def get(name):
        assert isinstance(name, str), name
        if name in Type._cache:
            symbol = Type._cache[name]
        else:
            symbol = Type._cache[name] = Type(name)
        return symbol

    def sexpr(self):
        return "<" + self._str() + ">"

    def is_super(self, other):
        assert isinstance(other, Type)
        if other in self._union:
            return self._union[other]
        unification = self._union[other] = self._is_super(other)
        return unification

    def _is_super(self, other):
        # TODO what about *actual* subtypes? do we care about those?
        if self is other:
            return Unification()


# TODO custom parametric types
class List(Type):
    _cache = {}

    def __init__(self, child):
        self.child = child
        self._union = {}
        self.has_generic = child.has_generic

    @staticmethod
    def get(child):
        assert isinstance(child, Type)
        if child in List._cache:
            type_ = List._cache[child]
        else:
            type_ = List._cache[child] = List(child)
        return type_

    def __repr__(self):
        return 'List({!r})'.format(self.child)

    def _str(self):
        return "List " + self.child._str()

    def _is_super(self, other):
        if isinstance(other, List):
            return self.child.is_super(other.child)

    def specialise(self, unification):
        return List.get(self.child.specialise(unification))


class Generic(Type):
    _cache = {}

    """a typevar."""
    def __init__(self, index):
        assert 1 <= index <= 26
        self.index = index
        self._union = {}
        self.has_generic = True

    def __repr__(self):
        return 'Generic({!r})'.format(self.index)

    def _str(self):
        return "'" + chr(96 + self.index)

    @staticmethod
    def get(index):
        assert isinstance(index, int), index
        if index in Generic._cache:
            type_ = Generic._cache[index]
        else:
            type_ = Generic._cache[index] = Generic(index)
        return type_

    def _is_super(self, other):
        if isinstance(other, Generic):
            # TODO what's the right thing to do here; 'a = 'b ?
            return
        return Unification({
            self.index: other,
        })

    def specialise(self, unification):
        return unification.values.get(self.index, self)


class Any(Type):
    def __init__(self):
        self._union = {}
        self.has_generic = False

    def __repr__(self):
        return "Type.ANY"

    def _str(self):
        return "Any"

    def _is_super(self, other):
        return Unification()


class Expr(Type):
    _rules = {}

    def __init__(self):
        self._union = {}
        self.has_generic = False

    def __repr__(self):
        return "Type.EXPR"

    def _str(self):
        return "Expr"


Type.PROGRAM = Type.get('Program')

# Expr -- a value which can fit into any slot
Type.EXPR = Type._cache['Expr'] = Expr()

# Type -- a slot which wants a type name
Type.TYPE = Type.get('Type')

# Any -- a slot which accepts any expression.
Type.ANY = Type._cache['Any'] = Any()


# make sure Type.get('List') fails!
Type._cache['List'] = None



class Unification:
    # specialise typevars.
    def __init__(self, values={}):
        #assert isinstance(values, dict)
        self.values = values

    def union(self, other):
        assert isinstance(other, Unification)
        for key in other.values:
            if key in self.values:
                # TODO is equality the right thing here?
                assert self.values[key] is other.values[key]
        values = self.values.copy()
        values.update(other.values)
        return Unification(values)

    def __repr__(self):
        if self.values:
            return "Unification({!r})".format(self.values)
        return "Unification()"

    def __str__(self):
        return "<" + ",\n ".join(str(Generic.get(i)) + " = " + str(t) for (i, t)
                in self.values.items()) + ">"

    def hash(self):
        return tuple(self.values.items())

