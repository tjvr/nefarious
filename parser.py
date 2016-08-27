
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
            return 'EOF', ''

        elif self.tok == '\n':
            self.next()
            while self.tok == ' ':
                self.next()
            return 'NEWLINE', '\n'

        elif self.tok == ' ':
            self.next()
            while self.tok == ' ':
                self.next()
            if self.tok == '\n':
                self.next()
                while self.tok == ' ':
                    self.next()
                return 'NEWLINE', '\n'
            return 'WHITESPACE', ' '

        elif self.tok in '\t\u000b\f\r':
            c = self.tok
            self.next()
            # error
            return 'ERROR', c

        elif self.tok in ":{}":
            c = self.tok
            self.next()
            return 'SPECIAL', c

        elif self.tok in "-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
            c = self.tok
            self.next()
            return 'PUNC', c

        else:
            s = self.tok
            self.next()
            while self.tok not in " \n\t\u000b\f\r:{}-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
                s += self.tok
                self.next()
            return 'WORD', s


def parse(source):
    lexer = Lexer(source)
    tok = lexer.lex()
    tokens = []
    while tok[0] != 'EOF':
        tokens.append(tok)
        tok = lexer.lex()
    return tokens

