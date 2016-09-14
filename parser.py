#import sys
#sys.setrecursionlimit(2000)

class Tree:
    def sexpr(self):
        raise NotImplementedError


class Tag(Tree):
    def expand(self, grammar):
        return [self]

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

    def __repr__(self):
        return 'Type({!r})'.format(self.name)

    def __str__(self):
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
        return "<" + str(self) + ">"

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

    def expand(self, grammar):
        return [self, Type.EXPR]

# TODO custom parametric types
class List(Type):
    _cache = {}

    def __init__(self, child):
        self.child = child
        self._union = {}

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

    def __str__(self):
        return "List " + str(self.child)

    def _is_super(self, other):
        if isinstance(other, List):
            return self.child.is_super(other.child)

    def expand(self, grammar):
        return [List.get(type_) for type_ in self.child.expand(grammar)] + [Type.EXPR]

    def specialise(self, unification):
        return List.get(self.child.specialise(unification))


class Generic(Type):
    _cache = {}

    """a typevar."""
    def __init__(self, index):
        assert 1 <= index <= 26
        self.index = index
        self._union = {}

    def __repr__(self):
        return 'Generic({!r})'.format(self.index)

    def __str__(self):
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
        if isinstance(other, Any):
            return
        return Unification({
            self.index: other,
        })

    def expand(self, grammar):
        return grammar.types + [Type.EXPR]

    def specialise(self, unification):
        return unification.values.get(self.index, self)


class Any(Type):
    def __init__(self):
        self._union = {}

    def __repr__(self):
        return "Type.ANY"

    def __str__(self):
        return "Any"

    def _is_super(self, other):
        return Unification()

    #def expand(self, grammar):
    #    return grammar.types



Type.PROGRAM = Type.get('Program')

# Expr -- a value which can fit into any slot
Type.EXPR = Type.get('Expr')

# Type -- a slot which wants a type name
Type.TYPE = Type.get('Type')

# Any -- a slot which accepts any expression.
Type.ANY = Type._cache['Any'] = Any()


# make sure Type.get('List') fails!
Type._cache['List'] = None



class Unification:
    # specialise typevars.
    def __init__(self, values=None):
        if values is None:
            values = {}
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

# test cases.
list_int = List.get(Type.get('Int'))
assert Type.get('Int').is_super(Type.get('Text')) == None
assert Type.get('Int').is_super(Type.get('Int')).values == {}
assert list_int.is_super(List(Type.get('Int'))).values == {}
assert Generic.get(2).is_super(Type.get('Int')).values == {2: Type.get('Int')}
assert List.get(Generic.get(1)).is_super(List.get(List.get(Type.get('Int')))).values == {1: List.get(Type.get('Int'))}



class Token(Tag):
    _cache = {}

    def __init__(self, kind, value=""):
        self.kind = kind
        self.value = value

    def __str__(self):
        return self.value or self.kind

    def __repr__(self):
        if self.value and self.value != ' ':
            return 'Token.word({!r})'.format(self.value)
        else:
            return 'Token.{}'.format(self.kind)

    @staticmethod
    def get(kind, value=""):
        assert isinstance(kind, str)
        assert isinstance(value, str)
        if kind == 'WS':
            value = ' '
        elif value:
            assert kind in ('RESERVED', 'PUNC', 'WORD', 'ERROR'), value
        key = kind, value
        if key in Token._cache:
            word = Token._cache[key]
        else:
            word = Token._cache[key] = Token(kind, value)
        return word

    @staticmethod
    def word(value):
        for c in value:
            if not (c.isalpha() or c.isdigit() or c == "_"):
                is_word = False
                break
        else:
            is_word = True
        if is_word:
            return Token.get('WORD', value)
        elif value in ":{}":
            return Token.get('RESERVED', value)
        elif value in "-!\"#$%&\\'()*+,./;<=>?@[]^`|~":
            return Token.get('PUNC', value)
        elif value == ' ':
            return Token.WS
        raise ValueError(value)

    def sexpr(self):
        return self.value or self.kind



# Match token kind, eg. NL
Token.EOF = Token.get('EOF')
Token.NL = Token.get('NL')
Token.WS = Token.get('WS', ' ')

# Match token value, eg. `+` or `while`
# nb. can *also* match on kind.
Token.RESERVED = Token.get('RESERVED')
Token.PUNC = Token.get('PUNC')
Token.WORD = Token.get('WORD')
Token.ERROR = Token.get('ERROR')

class Lexer:
    def __init__(self, source):
        self.source = source
        self.length = len(source)
        self.index = 0
        self.tok = source[0]

    def next(self):
        self.index += 1
        if self.index < self.length:
            self.tok = self.source[self.index]
        else:
            self.tok = ''

    def lex(self):
        if self.tok == '':
            return Token.EOF

        elif self.tok == '\n':
            self.next()
            while self.tok == ' ':
                self.next()
            return Token.NL

        elif self.tok == ' ':
            self.next()
            while self.tok == ' ':
                self.next()
            if self.tok == '\n':
                self.next()
                while self.tok == ' ':
                    self.next()
                return Token.NL
            return Token.WS

        elif self.tok in '\t\f\r':
            c = self.tok
            self.next()
            # error
            return Token.get('ERROR', c)

        elif self.tok in ":{}":
            c = self.tok
            self.next()
            return Token.get('RESERVED', c)

        elif self.tok in "-!\"#$%&\\'()*+,./;<=>?@[]^`|~":
            c = self.tok
            self.next()
            return Token.get('PUNC', c)

        # TODO _
        else:
            s = self.tok
            self.next()
            while self.tok not in " \n\t\f\r:{}-!\"#$%&\\'()*+,./;<=>?@[]^`|~":
                s += self.tok
                self.next()
            return Token.get('WORD', s)

    @staticmethod
    def tokenize(text):
        if not text: # TODO we shouldn't have to special-case this
            return []
        tokens = []
        lexer = Lexer(text)
        token = lexer.lex()
        while token != Token.EOF:
            tokens.append(token)
            token = lexer.lex()
        return tokens


class Rule:
    def __init__(self, target, symbols, call=None):
        assert isinstance(symbols, list)
        for s in symbols:
            assert isinstance(s, Tag)
        self.symbols = symbols
        self.target = target

        # TODO if target is Generic, same Generic must appear somewhere in
        # symbols.

        self.lr0s = []
        if symbols:
            self.first = previous = LR0(self, 0)
            self.lr0s.append(self.first)
            for dot in range(1, len(symbols)):
                lr0 = LR0(self, dot)
                self.lr0s.append(lr0)
                previous.advance = lr0
                previous = lr0
            previous.advance = target
        else:
            self.first = target

        self.priority = 0
        assert isinstance(call, Function)
        self.call = call

    def __repr__(self):
        return "<{} -> {}>".format(self.target, " ".join(map(str, self.symbols)))

    def specialise(self, unification):
        target = self.target.specialise(unification)
        symbols = [t.specialise(unification) for t in self.symbols]
        rule = Rule(target, symbols, self.call)
        rule.priority = self.priority
        return rule


class LR0(Tag):
    def __init__(self, rule, dot):
        self.rule = rule
        self.wants = rule.symbols[dot]
        self.advance = None # set by Rule
        self.dot = dot

    def __repr__(self):
        symbols = list(self.rule.symbols)
        symbols.insert(self.dot, ".")
        return "<{} -> {}>".format(self.rule.target, " ".join(map(str, symbols)))

    def specialise(self, unification):
        return self.rule.specialise(unification).lr0s[self.dot]


class Item:
    def __init__(self, start, tag, wanted_by):
        assert isinstance(tag, Tag), tag
        self.tag = tag
        self.start = start
        self.wanted_by = wanted_by
        self.generic_wants = None

        # derivation
        self.left = None
        self.right = None
        self.rule = None

        # evaluation
        self.value = None
        self.children = None

    def add_derivation(self, left, right, rule):
        if self.rule and self.rule.priority >= rule.priority:
            return
        self.left = left
        self.right = right
        self.rule = rule

    def __repr__(self):
        return "Item({!r}, {!r})".format(self.start, self.tag)

    def evaluate(self, stack=None):
        if self.value is not None:
            return self.value

        if stack is None:
            stack = []
        stack.append(self)
        rule = self.rule
        if not rule: # token
            return self.value

        children = self.evaluate_children(stack)

        value = build(rule, children)
        self.value = value
        assert stack.pop() == self
        return value

    def evaluate_children(self, stack):
        # nb. We don't cache children for intermediate nodes; we only cache the
        # value of completed nodes. So we-ll re-do building the list. This is
        # fine, because otherwise we'd end up copying the list anyway.
        if isinstance(self.tag, LR0) and self.tag.dot == 0:
            return []

        if self.children is not None:
            return list(self.children) # copy

        item = self
        stack = []
        while item.left:
            stack.append(item)
            item = item.left

        self.children = children = []
        for item in reversed(stack):
            child = item.right.evaluate(stack)
            # TODO this doesn't work for WS
            #assert child is not None, repr(item) + " RHS evaluated to None"
            children.append(child)

        return children



class Column:
    def __init__(self, grammar, index):
        self.grammar = grammar
        self.index = index
        self.items = []
        self.unique = {}
        self.wants = {}

    def want(self, item, type_):
        if type_ in self.wants:
            self.wants[type_].append(item)
        else:
            self.wants[type_] = [item]

    def add(self, start, tag, wanted_by):
        key = start, tag
        if key in self.unique:
            return self.unique[key]

        item = self.unique[key] = Item(start, tag, wanted_by)
        self.items.append(item)
        self.unique[key] = item

        if isinstance(tag, LR0) and not isinstance(tag.wants, Generic):
            self.want(item, tag.wants)
        return item

    def scan(self, word, previous):
        assert len(self.items) == 0
        if word.value:
            if word in previous.wants:
                item = self.add(previous.index, word, previous.wants[word])
                item.value = word
            token = Token.get(word.kind)
        else:
            token = word
        if token in previous.wants:
            item = self.add(previous.index, token, previous.wants[token])
            item.value = word
        return len(self.items) > 0

    def predict(self, tag):
        wanted_by = self.wants[tag]

        for target in self.grammar.expand(tag):
            for rule in self.grammar.get(target):
                item = self.add(self.index, rule.first, wanted_by)
                # nullables need a value!
                if not isinstance(rule.first, LR0) and rule.call: # is nullable
                    item.rule = rule

    def generics(self):
        for rule in self.grammar.get_generics():
            assert rule.target == Generic.get(1)
            item = self.add(self.index, rule.first, [])
            item.generic_wants = self.wants

    def complete(self, right):
        for left in right.wanted_by:

            tag = left.tag
            wanted_by = left.wanted_by
            if isinstance(tag.wants, Generic):
                if not isinstance(right.tag, Type):
                    continue

                unification = tag.wants.is_super(right.tag)
                if not unification:
                    # TODO warn?
                    continue
                old, tag = tag, tag.specialise(unification)
                assert old.rule.target.is_super(tag.rule.target)
                print old.rule.target, ':>', tag.rule.target

                if isinstance(left.tag.rule.target, Generic):
                    new_lhs = tag.rule.target
                    if new_lhs not in left.generic_wants:
                        # TODO warn?
                        continue
                    wanted_by = left.generic_wants[new_lhs]

            # assert other.tag.wants == item.tag
            new = self.add(left.start, tag.advance, wanted_by)
            new.add_derivation(left, right, tag.rule)
            new.generic_wants = left.generic_wants

    def predict_generic(self, item):
        if isinstance(item.tag.rule.target, Generic):
            for type_ in item.generic_wants.keys():
                self.want(item, type_)
                self.predict(type_)
        else:
            for type_ in self.grammar.expand(item.tag.wants):
                self.want(item, type_)
                self.predict(type_)

    def process(self):
        self.generics()

        for item in self.items:
            if isinstance(item.tag, LR0):
                target = item.tag.wants
                if isinstance(target, Generic):
                    self.predict_generic(item)
                else:
                    self.predict(target)
            else:
                self.complete(item)

    def evaluate(self):
        for item in self.items:
            if not isinstance(item.tag, LR0):
                item.evaluate()


class Grammar:
    def __init__(self):
        self.rule_sets = {}
        self.stack = [self.rule_sets]
        self.highest_priority = 0

        self.types = []
        # TODO scope Types?

    def add(self, target, symbols, call=None):
        rule = Rule(target, symbols, call)
        self.highest_priority += 1
        rule.priority = self.highest_priority

        if target not in self.rule_sets:
            self.rule_sets[target] = []
        self.rule_sets[target].append(rule)
        return rule

    def add_type(self, type_):
        self.types.append(type_)
        if isinstance(type_, List):
            return # TODO parametric rules
        self.add(Type.TYPE, [Token.word(type_.name)], TypeMacro)

    def remove(self, rule):
        # TODO should this traverse the stack?
        for rule_sets in reversed(self.stack):
            rules = rule_sets[target]
            if rule in rules:
                rules.remove(rule)
                return

    def get(self, target):
        matches = []
        for rule_sets in reversed(self.stack):
            if target in rule_sets:
                matches += rule_sets[target]
        return matches

    def get_generics(self):
        # TODO optimise
        for target in self.rule_sets:
            if isinstance(target, Generic):
                for x in self.rule_sets[target]:
                    yield x

    def save(self):
        assert self.stack[-1] is self.rule_sets
        self.rule_sets = {}
        self.stack.append(self.rule_sets)
        assert self.stack[-1] is self.rule_sets

    def restore(self):
        assert self.stack[-1] is self.rule_sets
        self.stack.pop()
        self.rule_sets = self.stack[-1]
        assert self.stack[-1] is self.rule_sets

    def add_list(self, target, cont):
        symbols = [target] + cont
        self.add(target, symbols, ContinueList)
        item = cont[-1]
        self.add(target, [item], StartList)

    def expand(self, tag):
        assert isinstance(tag, Type)
        targets = {}
        for x in tag.expand(self):
            targets[x] = None
        return targets.keys()


def build(rule, children):
    if rule.target == Type.PROGRAM:
        return children[0]
    return rule.call.build(children)


# two kinds of factories--
# * a Function pointer. From which, we build an AST node. This gets evaluated at runtime.
#
# * But! Sometimes we want to evaluate a rule at compile-time.
#   So, we invent Macros. These are just functions which are evaluated at
#   compile-time, and return a piece of AST.

class Function:
    def __init__(self, debug_name):
        assert isinstance(debug_name, str)
        self.debug_name = debug_name
        self.body = None

    def sexpr(self):
        return self.debug_name

    def set_body(self, body):
        assert isinstance(body, Body)
        self.body = body

    def build(self, children):
        return Call(self, children)

    def call_immediate(self, children):
        assert self.body is not None
        pass # TODO

class Macro(Function):
    def build(self, children):
        return self.call_immediate(children)

    def sexpr(self):
        assert False # macros should never be in the AST!

class Call(Tree):
    def __init__(self, func, args):
        self.func = func
        self.args = args

    def sexpr(self):
        return "(" + self.func.sexpr() + " " + " ".join(a.sexpr() for a in self.args) + ")"


grammar = Grammar()

def singleton(cls):
    return cls(cls.__name__)

DEFINE = Function('define')
# MACRO = Function('macro') # macro definitions do not get sent to the compiler!

# nullable whitespace derivation -- whitespace is always optional.
# note however that whitespace has to be explicitly allowed, eg. "Int <> Int"
# would not allow a space between < and >.
# ie. whitespace is only permitted if it appears in the definition.

@singleton
class Null(Macro):
    def build(self, values):
        return None

grammar.add(Token.WS, [], Null)

# For, um, lists.
# After all, this is "Nefarious Scheme"
LIST = Function('list')

@singleton
class StartList(Macro):
    def build(self, values):
        assert len(values) == 1
        child = values[0]
        return Call(LIST, [child])

@singleton
class ContinueList(Macro):
    def build(self, values):
        list_ = values[0]
        assert isinstance(list_, Call)
        assert list_[0].func is LIST
        list_[0].args.append(values[-1])
        return list_

# For, um, subtypes and stuff.
@singleton
class Identity(Macro):
    def build(self, values):
        assert len(values) == 1
        return values[0]

grammar.add_list(Type.get('SpecList'), [Type.get('Spec')])

grammar.add_list(Type.get('Block'), [Type.get('Line')])

# We want to--
# - allow for scoping the inside of blocks.
#   so eg. an `sql _` statement that accepts a block -- `sql { select * from ... }`
# - allow recursive definitions. `define fib Int:n { return fib ... }`
# - allow generic types. eg. (List 'a) -> (List 'a) "," 'a
#
# when *does* evaluation happen?
# is there a way to let evaluation affect prediction? That seems *somewhat*
# what we want to allow for here...
#
# Aside from generics, it would be fine if evaluation/scoping was hard-bound to
# { }...

# Generics.
# =========
#
# Prediction: ask Grammar for all subtypes of T.
# Always include "Expr".
# Generics expand to any type.   'a -> Expr, Int, Frac, Text ...
#
# Completion: unify right with left.wants. 
# Create new (but uniqued!) LR0s.
# right must be a *subtype* of left.wants!
# and target must be a *subtype* of the original wanted_by ~ target.
# Unification can fail!

#grammar.add_type(Type.EXPR)
# Don't need to add the Expr type -- grammar.expand() always returns it.

@singleton
class TypeMacro(Macro):
    def build(self, values):
        return Type.get(values[0].value)

grammar.add_type(Type.get('Int'))
grammar.add_type(Type.get('Text'))
grammar.add_type(Type.get('Bool'))
grammar.add_type(List.get(Generic.get(1)))

grammar.add(Type.ANY, [Generic.get(1)], Identity)
#grammar.add(Generic.get(1), [Type.EXPR], Identity)

# Generic parentheses!

@singleton
class Parens(Macro):
    def build(self, values):
        return values[2]
grammar.add(Generic.get(1), [Token.word("("), Token.WS, Generic.get(1), Token.WS, Token.word(")")], Parens)

CHOICE = Function('choice')
@singleton
class Choice(Macro):
    def build(self, values):
        return Call(CHOICE, [values[2], values[6]])
grammar.add(Generic.get(1), [Token.word("choose"), Token.WS, Generic.get(1), Token.WS, Token.word("or"), Token.WS, Generic.get(1)], Choice)

CMP = Function('cmp')
@singleton
class Cmp(Macro):
    def build(self, values):
        return Call(CMP, [values[0], values[4]])
grammar.add(Type.get('Bool'), [Generic.get(1), Token.WS, Token.word("<"), Token.WS, Generic.get(1)], Cmp)


#grammar.add(Type.PROGRAM, [Token.word('hello'), Token.NL], Function('hello'))

Int = Type.get('Int')
Text = Type.get('Text')
Bool = Type.get('Bool')

grammar.add(Type.PROGRAM, [Type.ANY, Token.NL], Identity)
#grammar.add(Type.ANY, [Int], Identity)
#grammar.add(Type.PROGRAM, [Int, Token.NL], Identity)
#grammar.add(Type.PROGRAM, [Text, Token.NL], Identity)
#grammar.add(Type.PROGRAM, [Bool, Token.NL], Identity)

grammar.add(Int, [Token.word('hello')], Identity)
grammar.add(Text, [Token.word('goodbye')], Identity)
grammar.add(Bool, [Token.word('false')], Identity)

grammar.add(Type.EXPR, [Token.word('foo')], Identity)


#grammar.add(List(Generic()), [Generic(), Token.WS, Generic()], StartList)
#grammar.add(List(Generic()), [List(Generic()), Token.WS, Generic()], ContinueList)

#grammar.add_list(List(Generic(0)), [Token.get(","), Generic(0)])

# grammar.add(Type.get('_PreDef'), [
#     Type.get('_PreDef'),
#     Type.get('Block'),
#     Token.get('{'),
# ], PreDef)
# 
# grammar.add(Type.get('Line'), [
#     Type.get('_PreDef'),
#     Type.get('Block'),
#     Token.get('}'),
# ], PostDef)



def parse(source):
    lexer = Lexer(source)

    column = Column(grammar, 0)
    column.wants[Type.PROGRAM] = []
    column.predict(Type.PROGRAM)
    column.process()

    grammar.save()
    grammar.restore()

    token = lexer.lex()
    index = 0
    line = ""
    while token != Token.EOF:
        if token != Token.NL:
            if token == Token.WS:
                line += " "
            else:
                line += token.value

        print index
        for item in column.items:
            print item
        print
        previous, column = column, Column(grammar, index + 1)
        if not column.scan(token, previous):
            msg = "Unexpected " + token.kind + " @ " + str(index)
            if token.value:
                msg += ": " + token.value
            for token in previous.wants:
                if isinstance(token, Token):
                    if token.value and token.value != ' ':
                        msg += "\nExpected: " + token.value
                    else:
                        msg += "\nExpected: " + token.kind
            msg += "\n>> " + line
            return msg
        column.process()

        if token == Token.word('{'):
            column.evaluate()
        elif token == Token.word('}'):
            column.evaluate()

        if token == Token.NL:
            line = ""

        token = lexer.lex()
        index += 1

    print index
    for item in column.items:
        print item
    print
    key = 0, Type.PROGRAM
    if key not in column.unique:
        msg = "Unexpected EOF"
        #for token in previous.wants:
        #    if isinstance(token, Token):
        #        if token.value and token.value != ' ':
        #            msg += "\nExpected: " + token.value
        #        else:
        #            msg += "\nExpected: " + token.kind
        #msg += "\n>> " + line
        return msg
    start = column.unique[key]
    value = start.evaluate()

    return value.sexpr()

