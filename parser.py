#import sys
#sys.setrecursionlimit(2000)

class Tag:
    pass

class Symbol(Tag):
    """A non-terminal / type name."""
    _cache = {}

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'Symbol({!r})'.format(self.name)

    def __str__(self):
        return self.name

    @staticmethod
    def get(name):
        assert isinstance(name, str), name
        if name in Symbol._cache:
            symbol = Symbol._cache[name]
        else:
            symbol = Symbol._cache[name] = Symbol(name)
        return symbol

Symbol.PROGRAM = Symbol.get('start')



class Token(Tag):
    _cache = {}

    def __init__(self, kind, value=""):
        self.kind = kind
        self.value = value

    def __str__(self):
        return self.value or self.kind

    def __repr__(self):
        if self.value:
            return 'Token.word({!r})'.format(self.value)
        else:
            return 'Token.{}'.format(self.kind)

    @staticmethod
    def get(kind, value=""):
        assert isinstance(kind, str)
        assert isinstance(value, str)
        if value:
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
        raise ValueError(value)


# Match token kind, eg. NL
Token.EOF = Token.get('EOF')
Token.NL = Token.get('NL')
Token.WS = Token.get('WS')

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
    def __init__(self, target, symbols, factory=None):
        assert isinstance(symbols, list)
        for s in symbols:
            assert isinstance(s, Tag)
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

        self.priority = 0
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

        if rule.target == Symbol.PROGRAM:
            value = children[0]
        elif rule.factory:
            value = rule.factory.build(children)
        else:
            value = Node(rule.target.name, children)
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
            assert child is not None, item
            children.append(child)

        return children



class Column:
    def __init__(self, grammar, index):
        self.grammar = grammar
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
        if word.value:
            if word in previous.wants:
                item = self.add(previous.index, word, previous.wants[word])
                item.value = Leaf(word)
            token = Token.get(word.kind)
        else:
            token = word
        if token in previous.wants:
            item = self.add(previous.index, token, previous.wants[token])
            item.value = Leaf(word)
        return len(self.items) > 0

    def predict(self, tag):
        wanted_by = self.wants[tag]
        for rule in self.grammar.get(tag):
            item = self.add(self.index, rule.first, wanted_by)
            # nullables need a value!
            if not isinstance(rule.first, LR0) and rule.factory: # is nullable
                item.rule = rule


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

    def evaluate(self):
        for item in self.items:
            if not isinstance(item.tag, LR0):
                item.evaluate()


class Grammar:
    def __init__(self):
        self.rule_sets = {}
        self.stack = [self.rule_sets]
        self.highest_priority = 0

    def add(self, target, symbols, factory=None):
        rule = Rule(target, symbols, factory)
        self.highest_priority += 1
        rule.priority = self.highest_priority

        if target not in self.rule_sets:
            self.rule_sets[target] = []
        self.rule_sets[target].append(rule)
        return rule

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

    def define(self, name, symbols, factory=None):
        return self.add(Symbol.get(name), symbols, factory)

    def define_builtin(self, output_type, spec, label=None):
        words = Lexer.tokenize(spec)

        symbols = []
        arg_indexes = []
        for index, word in enumerate(words):
            if word.value and word.value[0].isupper():
                symbols.append(Symbol.get(word.value))
                arg_indexes.append(index)
            else:
                symbols.append(word)

        if label is None:
            label = ''.join(('_' if w == Token.WS else w.value) for w in words)
        factory = NodeFactory(label, arg_indexes)
        return self.define(output_type, symbols, factory)

    def define_seq(self, name, symbol):
        self.add(Symbol.get(name), [symbol], BoxFactory(name))
        self.add(Symbol.get(name), [Symbol.get(name), symbol], ListFactory(name))

    def define_type(self, name):
        # Type -- a slot which wants a type name
        self.define('Type', [Token.word(name)]) #ConstantFactory(w_Type(name)))
        # Any -- a slot which accepts any expression
        self.define('Any', [Symbol.get(name)], NodeFactory(':'+name, [0]))
        # Expr -- a value which can fit into any slot
        self.define(name, [Symbol.get('Expr')], NodeFactory(':'+name, [0]))
        # Parens -- need a rule for each type!
        self.define(name, [
            Token.word('('), Token.WS, Symbol.get(name), Token.WS, Token.word(')')
        ], IdentityFactory(2))


class Tree:
    def __repr__(self):
        return "Tree"

class Node(Tree):
    def __init__(self, label, children):
        for c in children:
            assert isinstance(c, Tree), c
        self.label = label
        self.children = children

    def __repr__(self):
        return "Node({!r}, {!r})".format(self.label, self.children)

    def sexpr(self):
        sep = " "
        if self.label == "LineList":
            sep = "\n"
        return "(" + self.label + " " + sep.join([x.sexpr() for x in self.children]) + ")"

class Leaf(Tree):
    def __init__(self, token):
        assert isinstance(token, Token)
        self.token = token

    def __repr__(self):
        return "Leaf(" + repr(self.token) + ")"

    def sexpr(self):
        return self.token.value

class Literal(Tree):
    def __init__(self, value):
        assert isinstance(value, str)
        self.value = value

    def __repr__(self):
        return "Literal(" + repr(self.token) + ")"

    def sexpr(self):
        return self.value


class Factory:
    def __init__(self, process):
        self.process = process

    def build(self, values):
        return self.process(values)

class IdentityFactory(Factory):
    def __init__(self, index):
        self.index = index

    def build(self, values):
        return values[self.index]

class ListFactory(Factory):
    def __init__(self, label):
        self.label = label

    def build(self, values):
        node, child = values
        list_ = node.children
        list_.append(child)
        return Node(self.label, list_)

class BoxFactory(ListFactory):
    def build(self, symbols):
        return Node(self.label, [symbols[0]])

class EmptyListFactory(ListFactory):
    def build(self, symbols):
        return Node(self.label, [])

class NodeFactory(Factory):
    def __init__(self, label, arg_indexes):
        self.label = label
        self.arg_indexes = arg_indexes

    def build(self, values):
        args = []
        for index in self.arg_indexes:
            args.append(values[index])
        return Node(self.label, args)


# nullable whitespace derivation -- whitespace is always optional.
# note however that whitespace has to be explicitly allowed, eg. "Int +- Int"
# would not allow a space between + and -.
# ie. whitespace is only permitted if it appears in the definition.

def whitespace(null):
    return Literal("")

grammar = Grammar()
grammar.add(Token.WS, [], Factory(whitespace))

STAR = Token.word('*')
COLON = Token.word(':')
TYPE = Symbol.get('Type')
grammar.define('Spec', [Token.WS])
grammar.define('Spec', [Token.WORD], NodeFactory('WORD', [0]))
grammar.define('Spec', [Token.PUNC], NodeFactory('PUNC', [0]))
grammar.define('Spec', [COLON, TYPE])
grammar.define('Spec', [COLON, STAR, TYPE])
grammar.define('Spec', [Token.WORD, COLON, TYPE])
grammar.define('Spec', [Token.WORD, COLON, STAR, TYPE])

grammar.define_seq('SpecList', Symbol.get('Spec'))

def predef(values):
    _define, _ws, spec_list, _ = values

    label_parts = []
    symbols = []
    arg_indexes = []
    arguments = []
    for spec in spec_list.children:
        index = len(symbols)
        kind = spec.label
        spec = spec.children
        is_list = False
        if len(spec) == 4:
            name, _, _, type_ = spec
            is_list = True
            assert name.token.kind == 'WORD'
            name = name.token.value
        
        elif len(spec) == 3:
            name, _, type_ = spec
            assert name.token.kind == 'WORD'
            name = name.token.value

        elif len(spec) == 2:
            is_list = True
            _, type_ = spec
            name = "_" + str(len(arguments) + 1)

        else:
            leaf = spec[0]
            if isinstance(leaf, Literal):
                if leaf.value == "": # null whitespace
                    continue
                assert False
            token = leaf.token

            if token == Token.WS:
                label_parts.append('_')
            else:
                assert token.value, token
                label_parts.append(token.value)
            symbols.append(token)
            continue

        type_ = type_.children[0].token.value

        arg_indexes.append(index)
        symbols.append(Symbol.get(type_))
        arguments.append(Node('arg', [Literal(name), Literal(type_)]))
        label_parts.append(type_)

    assert symbols.pop() == Token.WS
    assert label_parts.pop() == "_"
    label = ''.join(label_parts)

    output_type = 'Int' # TODO type checking? [need body first!]

    rule = grammar.define(output_type, symbols, NodeFactory(label, arg_indexes))

    grammar.save()

    for arg in arguments:
        name, type_ = arg.children
        assert isinstance(type_, Literal)
        assert isinstance(type_, Literal)
        type_ = type_.value
        q = grammar.define(type_, [Token.word(name.value)], NodeFactory('GetVar', [0]))

    return Node('predef', [Literal(label), Node('args', arguments)])

def postdef(values):
    predef, body, _ = values
    label, arguments = predef.children

    grammar.restore()

    names = [arg.children[0] for arg in arguments.children]

    return Node('def', [label, Node('args', names), body]) #, Node('body', body)])

def body(values):
    _, lines, _ = values
    return lines

def empty_body(values):
    return Node('LineList', [])

def deftype(values):
    token = values[2].token
    grammar.define_type(token.value)
    return Node('deftype', [Literal(token.value)])

grammar.define('PreDef', [Token.word('define'), Token.WS, Symbol.get('SpecList'), Token.word('{')], Factory(predef))
grammar.define('Line', [Symbol.get('PreDef'), Symbol.get('Body'), Token.word('}')], Factory(postdef))
grammar.define('Body', [Token.WS, Symbol.get('LineList'), Token.WS], Factory(body))
grammar.define('Body', [Token.WS], Factory(empty_body))

grammar.define('Line', [Token.word('deftype'), Token.WS, Token.WORD], Factory(deftype))

grammar.add(Symbol.PROGRAM, [Symbol.get("LineList")])
grammar.define_seq("LineList", Symbol.get("Line"))
grammar.define("Line", [Symbol.get("Int"), Token.NL], IdentityFactory(0))
grammar.define("Line", [Token.NL], NodeFactory('Empty', []))

grammar.define_type('Int')
grammar.define_type('List')

grammar.define_builtin('Line', 'Opcode')
grammar.define_builtin('Opcode', 'PRINT')
grammar.define_builtin('Opcode', 'PUSH Any')
grammar.define_builtin('Opcode', 'INT_ADD')
grammar.define_builtin('Opcode', 'INT_TO_STR')

# later definitions will override earlier ones.
# However, earlier definitions bind tighter than later ones!

grammar.define_builtin('Int', 'Int * Int').priority = grammar.define_builtin('Int', 'Int / Int').priority
grammar.define_builtin('Int', 'Int + Int').priority = grammar.define_builtin('Int', 'Int - Int').priority
grammar.define_builtin('Bool', 'Int < Int')
grammar.define_builtin('Int', 'distance to x: Int y: Int')
grammar.define_builtin('Line', 'print Int')
grammar.define_builtin('Line', 'return Any')
grammar.define_builtin('Line', 'if Bool then Block')
#grammar.define_builtin('Line', 'if Bool then Block else Line')
#grammar.define_builtin('Line', 'Block')

grammar.define('Block', [Token.word('{'), Symbol.get('Body'), Token.word('}')], IdentityFactory(1))

grammar.define("Int", [Token.word("1")])
grammar.define("Int", [Token.word("2")])
grammar.define("Int", [Token.word("3")])
grammar.define("Int", [Token.word("4")])
grammar.define("Int", [Token.word("5")])


def parse(source):
    lexer = Lexer(source)

    column = Column(grammar, 0)
    column.wants[Symbol.PROGRAM] = []
    column.predict(Symbol.PROGRAM)
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

        #print index, column.items
        previous, column = column, Column(grammar, index + 1)
        if not column.scan(token, previous):
            msg = "Unexpected " + token.kind + " @ " + str(index)
            if token.value:
                msg += ": " + token.value
            for token in previous.wants:
                if isinstance(token, Token):
                    if token.value:
                        assert not isinstance(token.value, Leaf) # TODO remove
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

    #print index, column.items
    key = 0, Symbol.PROGRAM
    if key not in column.unique:
        return "Unexpected EOF"
    start = column.unique[key]
    value = start.evaluate()

    return value.sexpr() #"yay"

