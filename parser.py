
def tokenize(source):
    index = 0
    tok = source[0]

    def next():
        index += 1
        if index < len(source):
            tok = source[index]
        else:
            tok = ''

    def lex():
        if tok == '':
            return 'EOF', ''

        elif tok == '\n':
            next()
            while tok == ' ':
                next()
            return 'NEWLINE', '\n'

        elif tok == ' ':
            next()
            while tok == ' ':
                next()
            if tok == '\n':
                next()
                while tok == ' ':
                    next()
                return 'NEWLINE', '\n'
            return 'WHITESPACE', ' '

        elif tok in '\t\u000b\f\r':
            c = tok
            next()
            # error
            return 'ERROR', c

        elif tok in ":{}":
            c = tok
            next()
            return 'SPECIAL', c

        elif tok in "-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
            c = tok
            next()
            return 'PUNC', c

        else:
            s = tok
            next()
            while tok not in " \n\t\u000b\f\r:{}-!\"#$%&\\'()*+,./;<=>?@[]^_`|~":
                s += tok
                next()
            return s

    return lex

def parse(source):
    lex = tokenize(source)
    tok = lex()
    tokens = []
    while tok:
        tokens.push(tok)
        tok = lex()
    return tokens

