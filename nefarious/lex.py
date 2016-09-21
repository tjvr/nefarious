
from .types import Tag

# TODO Digit tokens


class Word(Tag):
    _cache = {}
    has_generic = False

    def __init__(self, kind, value=""):
        self.kind = kind
        self.value = value
        self.has_value = bool(len(self.value) and self.kind != 'WS' and self.kind != 'NL')

    def __str__(self):
        return self.value or self.kind

    def __repr__(self):
        if self.value and self.value != ' ':
            return 'Word.word({!r})'.format(self.value)
        else:
            return 'Word.{}'.format(self.kind)

    @staticmethod
    def get(kind, value=""):
        assert isinstance(kind, str)
        assert isinstance(value, str)
        if value:
            assert kind in ('RESERVED', 'PUNC', 'WORD', 'ERROR', 'WS'), value
        key = kind, value
        if key in Word._cache:
            word = Word._cache[key]
        else:
            word = Word._cache[key] = Word(kind, value)
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
            return Word.get('WORD', value)
        elif value in ":{}":
            return Word.get('RESERVED', value)
        elif value in "-!\"#$%&\\'()*+,./;<=>?@[]^`|~":
            return Word.get('PUNC', value)
        elif value == ' ':
            return Word.WS
        raise ValueError(value)

    def sexpr(self):
        return self.value if self.has_value else self.kind


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
            return Word.EOF

        elif self.tok == '\n':
            self.next()
            while self.tok == ' ':
                self.next()
            return Word.NL

        elif self.tok == ' ':
            self.next()
            while self.tok == ' ':
                self.next()
            if self.tok == '\n':
                self.next()
                while self.tok == ' ':
                    self.next()
                return Word.NL
            return Word.WS

        elif self.tok in '\t\f\r':
            c = self.tok
            self.next()
            # error
            return Word.get('ERROR', c)

        elif self.tok in ":{}":
            c = self.tok
            self.next()
            return Word.get('RESERVED', c)

        elif self.tok in "-!\"#$%&\\'()*+,./;<=>?@[]^`|~":
            c = self.tok
            self.next()
            return Word.get('PUNC', c)

        # TODO _
        else:
            s = self.tok
            self.next()
            while self.tok not in " \n\t\f\r:{}-!\"#$%&\\'()*+,./;<=>?@[]^`|~":
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
        while token != Word.EOF:
            tokens.append(token)
            token = lexer.lex()
        return tokens


# Match token kind, eg. NL
Word.EOF = Word.get('EOF')
Word.NL = Word.get('NL')
Word.WS = Word.get('WS', ' ')
Word.NULL_WS = Word.get('WS', '')
Word.WS_NOT_NULL = Word.get('WS', '  ')

# Match token value, eg. `+` or `while`
# nb. can *also* match on kind.
Word.RESERVED = Word.get('RESERVED')
Word.PUNC = Word.get('PUNC')
Word.WORD = Word.get('WORD')
Word.ERROR = Word.get('ERROR')

Word.ENTER = Word.word("{")
Word.EXIT = Word.word("}")
