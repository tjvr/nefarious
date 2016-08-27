
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

    @classmethod
    def get(self, kind):
        if kind in self._cache:
            token = self._cache[kind]
        else:
            token = self._cache[kind] = Token(kind)
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

    @classmethod
    def get(self, kind, value):
        key = kind, value
        if key in self._cache:
            word = self._cache[key]
        else:
            word = self._cache[key] = Word(kind, value)
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
            return Token.EOF, ''

        elif self.tok == '\n':
            self.next()
            while self.tok == ' ':
                self.next()
            return Token.NEWLINE, '\n'

        elif self.tok == ' ':
            self.next()
            while self.tok == ' ':
                self.next()
            if self.tok == '\n':
                self.next()
                while self.tok == ' ':
                    self.next()
                return Token.NEWLINE, '\n'
            return Token.WHITESPACE, ' '

        elif self.tok in '\t\u000b\f\r':
            c = self.tok
            self.next()
            # error
            return Token.ERROR, c

        elif self.tok in ":{}":
            c = self.tok
            self.next()
            return Token.RESERVED, c

        elif self.tok in "-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
            c = self.tok
            self.next()
            return Token.PUNC, c

        else:
            s = self.tok
            self.next()
            while self.tok not in " \n\t\u000b\f\r:{}-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
                s += self.tok
                self.next()
            return Token.WORD, s


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
        if name in self._cache:
            symbol = self._cache[name]
        else:
            symbol = self._cache[name] = Symbol(name)
        return symbol

    def add_rule(self, symbols, process=None):
        self.rule_set.append(Rule(self, symbols, process))

Symbol.START = Symbol.get('start')


class Rule:
    highest_priority = 0

    def __init__(self, target, symbols, process=None):
        assert isinstance(symbols, list)
        assert all(isinstance(s, Tag) for s in symbols)
        self.symbols = symbols
        self.target = target

        self.first = previous = LR0(self, 0)
        for dot in range(1, len(symbols)):
            lr0 = LR0(self, dot)
            previous.advance = lr0
            previous = lr0
        lr0.advance = target

        Rule.highest_priority += 1
        self.priority = Rule.highest_priority
        self.process = process


class LR0(Tag):
    def __init__(self, rule, dot):
        self.rule = rule
        self.wants = rule.symbols[dot]
        self.advance = None # set by Rule

        self.dot = dot # for debugging

    def __repr__(self):
        symbols = self.rule.symbols
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

    def scan(self, token, value, previous):
        success = False
        if token in previous.wants:
            self.add(previous.index, token, previous.wants[token])
            success = True
        if value:
            word = Word.get(token.kind, value)
            if word in previous.wants:
                self.add(previous.index, token, previous.wants[word])
                success = True
        return success

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


Symbol.START.add_rule([Word.get("WORD", "1"), Word.get("PUNC", "+"), Word.get("WORD", "2")])

def parse(source):
    lexer = Lexer(source)

    column = Column(0)
    column.wants[Symbol.START] = []
    column.predict(Symbol.START)
    column.process()

    tok = lexer.lex()
    index = 0
    while tok[0] != Token.EOF:
        previous, column = column, Column(index + 1)
        token, value = tok
        if not column.scan(token, value, previous):
            return "Unexpected " + token.kind + " @ " + str(index) + ": " + value
        column.process()
        print index, column.items
        tok = lexer.lex()
        index += 1

    column.unique[0, Symbol.START]

    return "yay"

