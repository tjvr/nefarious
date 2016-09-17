
class Tree:
    def sexpr(self):
        raise NotImplementedError


class Tag(Tree):
    def specialise(self, unification):
        return self

    def is_super(self, other):
        if self is other:
            return Unification.EMPTY

    def supertypes(self):
        return [self]

    def subtypes(self):
        return [self]



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
        return "Unification.EMPTY"

    def __str__(self):
        return "<" + ",\n ".join(str(Generic.get(i)) + " = " + str(t) for (i, t)
                in self.values.items()) + ">"

    def hash(self):
        return tuple(self.values.items())

Unification.EMPTY = Unification()



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
        if other.has_generic:
            # TODO I'm not sure about this...
            result = Unification.EMPTY
        else:
            result = self._is_super(other)
        unification = self._union[other] = result
        return unification

    def _is_super(self, other):
        if self is other:
            return Unification.EMPTY

    def supertypes(self):
        return [Type.ANY, self]

    def subtypes(self):
        return [self, Generic.ALPHA]


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

    def supertypes(self):
        l = [Type.ANY]
        for t in self.child.supertypes():
            l.append(List.get(t))
        return l

    def subtypes(self):
        l = []
        for t in self.child.subtypes():
            l.append(List.get(t))
        l.append(Generic.ALPHA)
        return l

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
            # TODO 'a = 'b
            # - return a Unification 'a -> 'b; not sure which way round though!
            # (might be 'b -> 'a).

            # TODO alpha-rename before unifying.
            return
        return Unification({
            self.index: other,
        })

    def specialise(self, unification):
        return unification.values.get(self.index, self)

    def supertypes(self):
        return [Generic.ALPHA]

    def subtypes(self):
        return [Type.ANY, Generic.ALPHA]

Generic.ALPHA = Generic.get(1)


class Any(Type):
    def __init__(self):
        self._union = {}
        self.has_generic = False

    def __repr__(self):
        return "Type.ANY"

    def _str(self):
        return "Any"

    def _is_super(self, other):
        return Unification.EMPTY

    def supertypes(self):
        return [Type.ANY]

    def subtypes(self):
        return [Type.ANY, Generic.ALPHA]



class Program(Type):
    def __init__(self):
        self._union = {}
        self.has_generic = False

    def __repr__(self):
        return "Type.PROGRAM"

    def _str(self):
        return "Program"

    def supertypes(self):
        return [Type.PROGRAM]

    def subtypes(self):
        return [Type.PROGRAM]



Type.PROGRAM = Type._cache['Program'] = Program()

# Wild -- a value which can fit into any slot
# REMOVED -- use Generics instead.

# Type -- a slot which wants a type name
Type.TYPE = Type.get('Type')

# Any -- a slot which accepts any expression.
Type.ANY = Type._cache['Any'] = Any()


# make sure Type.get('List') fails!
Type._cache['List'] = None


