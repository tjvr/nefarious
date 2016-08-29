#import sys
#sys.setrecursionlimit(2000)

class Tag:
    rule_set = []


class Token(Tag):
    """Match token kind, eg. NEWLINE"""
    _cache = {}

    def __init__(self, kind):
        self.kind = kind

    def __str__(self):
        return self.kind

    def __repr__(self):
        return 'Token({!r})'.format(self.kind)

    @staticmethod
    def get(kind):
        if kind in Token._cache:
            token = Token._cache[kind]
        else:
            token = Token._cache[kind] = Token(kind)
        return token

Token.ERROR = Token.get('ERROR')
Token.EOF = Token.get('EOF')
Token.NEWLINE = Token.get('NEWLINE')
Token.WHITESPACE = Token.get('WHITESPACE')
Token.RESERVED = Token.get('RESERVED')
Token.PUNC = Token.get('PUNC')
Token.WORD = Token.get('WORD')


class Word(Tag):
    """Match token value, eg. `+` or `while` """
    _cache = {}

    def __init__(self, kind, value):
        self.kind = kind
        self.value = value

    def __str__(self):
        return repr(self.value)

    def __repr__(self):
        return 'Word({!r}, {!r})'.format(self.kind, self.value)

    @staticmethod
    def get(kind, value):
        assert kind in ('RESERVED', 'PUNC', 'WORD', 'ERROR'), kind
        key = kind, value
        if key in Word._cache:
            word = Word._cache[key]
        else:
            word = Word._cache[key] = Word(kind, value)
        return word


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
            return Token.NEWLINE

        elif self.tok == ' ':
            self.next()
            while self.tok == ' ':
                self.next()
            if self.tok == '\n':
                self.next()
                while self.tok == ' ':
                    self.next()
                return Token.NEWLINE
            return Token.WHITESPACE

        elif self.tok in '\t\u000b\f\r':
            c = self.tok
            self.next()
            # error
            return Word.get('ERROR', c)

        elif self.tok in ":{}":
            c = self.tok
            self.next()
            return Word.get('RESERVED', c)

        elif self.tok in "-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
            c = self.tok
            self.next()
            return Word.get('PUNC', c)

        else:
            s = self.tok
            self.next()
            while self.tok not in " \n\t\u000b\f\r:{}-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
                s += self.tok
                self.next()
            return Word.get('WORD', s)

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


class Symbol(Tag):
    """A non-terminal."""
    _cache = {}

    def __init__(self, name):
        self.name = name
        self.rule_set = []

    def __repr__(self):
        return 'Symbol({!r})'.format(self.name)

    def __str__(self):
        return self.name

    @classmethod
    def get(self, name):
        assert isinstance(name, str)
        if name in self._cache:
            symbol = self._cache[name]
        else:
            symbol = self._cache[name] = Symbol(name)
        return symbol

    def add_rule(self, symbols, factory=None):
        rule = Rule(self, symbols, factory)
        self.rule_set.append(rule)
        return rule

Symbol.START = Symbol.get('start')


class Rule:
    highest_priority = 0

    def __init__(self, target, symbols, factory=None):
        assert isinstance(symbols, list)
        assert all(isinstance(s, Tag) for s in symbols)
        self.symbols = symbols
        self.target = target

        if symbols:
            self.first = previous = LR0(self, 0)
            for dot in range(1, len(symbols)):
                lr0 = LR0(self, dot)
                previous.advance = lr0
                previous = lr0
            previous.advance = target
        else:
            self.first = target

        Rule.highest_priority += 1
        self.priority = Rule.highest_priority
        self.factory = factory

    def __repr__(self):
        return "<{} -> {}>".format(self.target, " ".join(map(str, self.symbols)))

class LR0(Tag):
    def __init__(self, rule, dot):
        self.rule = rule
        self.wants = rule.symbols[dot]
        self.advance = None # set by Rule

        self.dot = dot # for debugging

    def __repr__(self):
        symbols = list(self.rule.symbols)
        symbols.insert(self.dot, ".")
        return "<{} -> {}>".format(self.rule.target, " ".join(map(str, symbols)))


class Item:
    def __init__(self, start, tag, wanted_by):
        assert isinstance(tag, Tag), tag
        self.tag = tag
        self.start = start
        self.wanted_by = wanted_by

        # derivation
        self.left = None
        self.right = None
        self.rule = None

        # evaluation
        self.value = None

    def add_derivation(self, left, right, rule):
        if self.rule and self.rule.priority >= rule.priority:
            return
        self.left = left
        self.right = right
        self.rule = rule

    def __repr__(self):
        return "Item({!r}, {!r})".format(self.start, self.tag)

    def evaluate(self):
        if self.value is not None:
            return self.value

        rule = self.rule
        if not rule: # token
            return self.value

        children = []
        if True: #not rule.is_nullable:
            children = self.evaluate_children()
            children = list(children) # copy
        if rule.target == Symbol.START:
            value = children[0]
        elif rule.factory:
            value = rule.factory.build(children)
        else:
            value = Node(rule.target.name, children)
        self.value = value
        return value

    def evaluate_children(self):
        # nb. We don't cache children for intermediate nodes; we only cache the
        # value of completed nodes. So we-ll re-do building the list. This is
        # fine, because otherwise we'd end up copying the list anyway.
        if isinstance(self.tag, LR0) and self.tag.dot == 0:
            return []

        item = self
        stack = []
        while item.left:
            stack.append(item)
            item = item.left

        children = []
        for item in reversed(stack):
            child = item.right.evaluate()
            children.append(child)

        return children



class Column:
    def __init__(self, index):
        self.index = index
        self.items = []
        self.unique = {}
        self.wants = {}

    def add(self, start, tag, wanted_by):
        key = start, tag
        if key in self.unique:
            return self.unique[key]

        item = self.unique[key] = Item(start, tag, wanted_by)
        self.items.append(item)
        self.unique[key] = item

        if isinstance(tag, LR0):
            if tag.wants in self.wants:
                self.wants[tag.wants].append(item)
            else:
                self.wants[tag.wants] = [item]
        return item

    def scan(self, word, previous):
        assert len(self.items) == 0
        if isinstance(word, Word):
            if word in previous.wants:
                item = self.add(previous.index, word, previous.wants[word])
                item.value = Leaf(word.value)
            token = Token.get(word.kind)
        else:
            token = word
        if token in previous.wants:
            item = self.add(previous.index, token, previous.wants[token])
            item.value = Leaf(token.kind)
        return len(self.items) > 0

    def predict(self, tag):
        wanted_by = self.wants[tag]
        for rule in tag.rule_set:
            self.add(self.index, rule.first, wanted_by)

    def complete(self, right):
        for left in right.wanted_by:
            # assert other.tag.wants == item.tag
            new = self.add(left.start, left.tag.advance, left.wanted_by)
            new.add_derivation(left, right, left.tag.rule)

    def process(self):
        for item in self.items:
            if isinstance(item.tag, LR0):
                self.predict(item.tag.wants)
            else:
                self.complete(item)


class BaseNode:
    def __repr__(self):
        return "BaseNode"

class Node(BaseNode):
    def __init__(self, label, children):
        self.label = label
        self.children = children

    def __repr__(self):
        return "Node({!r}, {!r})".format(self.label, self.children)

    def sexpr(self):
        return "(" + self.label + " " + " ".join([x.sexpr() for x in self.children]) + ")"

class Leaf(BaseNode):
    def __init__(self, token):
        self.token = token

    def __repr__(self):
        return "Leaf(" + repr(self.token) + ")"

    def sexpr(self):
        return self.token


def define(named_words, output_type, body, label=None):
    target = Symbol.get(output_type)
    arg_indexes = []
    arg_names = []
    symbols = []
    label_parts = []
    for index, (name, word) in enumerate(named_words):
        if name is None:
            assert isinstance(word, Word)
            symbols.append(word)
            label_parts.append(word.value)
        else:
            assert isinstance(word, Symbol)
            symbols.append(your_mother)
            arg_indexes.append(index)
            arg_indexes.append(name)
    if label is None:
        label = " ".join(label_parts)
    process = NodeFactory()
    Symbol.get()

def define_builtin(output_type, spec, label=None):
    words = Lexer.tokenize(spec)

    symbols = []
    arg_indexes = []
    for index, word in enumerate(words):
        value = word.value if isinstance(word, Word) else None
        if value and value[0].isupper():
            symbols.append(Symbol.get(word.value))
            arg_indexes.append(index)
        else:
            symbols.append(word)

    if label is None:
        label = ''.join(('_' if w == Token.WHITESPACE else w.value) for w in words)
    factory = NodeFactory(label, arg_indexes)
    rule = Symbol.get(output_type).add_rule(symbols, factory)
    return rule


class Factory:
    def __init__(self, process):
        self.process = process

    def build(self, symbols):
        return self.process(symbols)


class NodeFactory(Factory):
    def __init__(self, label, arg_indexes):
        self.label = label
        self.arg_indexes = arg_indexes

    def build(self, symbols):
        args = []
        for index in self.arg_indexes:
            args.append(symbols[index])
        if self.label == 'IDENTITY':
            return args[0]
        return Node(self.label, args)


# nullable whitespace derivation -- whitespace is always optional.
# note however that whitespace has to be explicitly allowed, eg. "Int +- Int"
# would not allow a space between + and -.
# ie. whitespace is only permitted if it appears in the definition.

Token.WHITESPACE.rule_set = [Rule(Token.WHITESPACE, [])]

define_rule('Spec', [Token.WORD])
define_rule('Spec', [Token.PUNC])
define_rule('Spec', [Symbol.get('Type')])
define_rule('Spec', [Word.get('PUNC', '*'), Symbol.get('Type')])

define_list('SpecList', Symbol.get('Spec'))

def predef(symbols):
    define, _ws, spec_list, _ = symbols
    # TODO
    return label, names

def postdef(symbols):
    predef, body, _ = symbols
    # TODO
    return body

define_rule('PreDef', [Symbol.get('define'), Token.WHITESPACE, Symbol.get('SpecList'), Word.get('RESERVED', '{')])
define_rule('PostDef', [Symbol.get('PreDef'), Symbol.get('Body'), Word.get('RESERVED', '}')])

define_rule('Type', [Word.get('WORD', 'Int')])

define_builtin('Int', 'Int * Int').priority = define_builtin('Int', 'Int / Int').priority
define_builtin('Int', 'Int + Int').priority = define_builtin('Int', 'Int - Int').priority
define_builtin('Int', 'distance to x: Int y: Int')
define_builtin('Int', '( Int )', 'IDENTITY')

# later definitions will override earlier ones.
# However, earlier definitions bind tighter than later ones!

Symbol.START.add_rule([Symbol.get("Int")])
Symbol.get('Int').add_rule([Word.get("WORD", "1")])
Symbol.get('Int').add_rule([Word.get("WORD", "2")])
Symbol.get('Int').add_rule([Word.get("WORD", "3")])
Symbol.get('Int').add_rule([Word.get("WORD", "4")])
Symbol.get('Int').add_rule([Word.get("WORD", "5")])

def parse(source):
    lexer = Lexer(source)

    column = Column(0)
    column.wants[Symbol.START] = []
    column.predict(Symbol.START)
    column.process()

    token = lexer.lex()
    index = 0
    while token != Token.EOF:
        #print index, column.items
        previous, column = column, Column(index + 1)
        if not column.scan(token, previous):
            msg = "Unexpected " + token.kind + " @ " + str(index)
            if isinstance(token, Word):
                msg += ": " + token.value
            return msg
        column.process()
        token = lexer.lex()
        index += 1

    #print index, column.items
    key = 0, Symbol.START
    if key not in column.unique:
        return "Unexpected EOF"
    start = column.unique[key]
    value = start.evaluate()

    return value.sexpr() #"yay"

