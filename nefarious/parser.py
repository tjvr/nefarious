#import sys
#sys.setrecursionlimit(2000)

from .types import *
from .lex import Word, Lexer
from .grammar import Function, CoerceMacro


DEBUG = False

class Rule:
    def __init__(self, target, symbols, call=None):
        assert isinstance(symbols, list)
        for s in symbols:
            assert isinstance(s, Tag)
        self.symbols = symbols
        self.target = target

        self._specialise = {}

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
        rule = self
        indexes = unification.values.keys()
        # TODO sort indexes
        for index in indexes:
            type_ = unification.values[index]
            rule = rule._specialise_once(index, type_)
        return rule

    def _specialise_once(self, index, type_):
        key = index, type_
        if key in self._specialise:
            return self._specialise[key]

        u = Unification({index: type_})
        target = self.target.specialise(u)
        symbols = [t.specialise(u) for t in self.symbols]
        rule = Rule(target, symbols, self.call)
        rule.priority = self.priority
        self._specialise[key] = rule
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
        #return "Item({!r}, {!r})".format(self.start, self.tag)
        if self.generic_wants:
            return "Item({!r}, {!r}, <{}>)".format(self.start, self.tag,
                    ", ".join(str(t) for t in self.generic_wants.keys() if isinstance(t, Type)))
        else:
            return "Item({!r}, {!r}, [{}])".format(self.start, self.tag,
                    ", ".join(str(item.tag.rule.target) for item in self.wanted_by))

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

        if rule.target == Type.PROGRAM:
            value = children[0]
        else:
            value = rule.call.build(children)

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
            assert child is not None, "item RHS evaluated to None"
            children.append(child)

        return children



class Column:
    def __init__(self, grammar, index):
        self.grammar = grammar
        self.index = index
        self.items = []
        self.unique = {}
        self.wants = {}
        self.wants_generic = []

    def want(self, item, type_):
        if type_ in self.wants:
            self.wants[type_].append(item)
        else:
            self.wants[type_] = [item]

    def has(self, start, tag):
        key = start, tag
        if key in self.unique:
            return self.unique[key]

    def add(self, start, tag, wanted_by):
        key = start, tag
        if key in self.unique:
            return self.unique[key]

        item = self.unique[key] = Item(start, tag, wanted_by)
        self.items.append(item)
        self.unique[key] = item

        if isinstance(tag, LR0) and not tag.wants.has_generic:
            self.want(item, tag.wants)
        return item

    def scan(self, word, previous):
        assert isinstance(word, Word)
        assert len(self.items) == 0
        if word.has_value:
            if word in previous.wants:
                item = self.add(previous.index, word, previous.wants[word])
                item.value = word
            token = Word.get(word.kind)
        else:
            token = word
        if token in previous.wants:
            item = self.add(previous.index, token, previous.wants[token])
            item.value = word
        return len(self.items) > 0

    def predict(self, tag):
        wanted_by = self.wants[tag]

        for item in self.wants_generic:
            if item not in wanted_by:
                wanted_by.append(item)

        for target in self.grammar.expand(tag):
            for rule in self.grammar.get(target):
                item = self.add(self.index, rule.first, wanted_by)
                # nullables need a value!
                if not isinstance(rule.first, LR0) and rule.call: # is nullable
                    item.rule = rule

                if target.has_generic:
                    item.generic_wants = {}

        self.predict_expr(tag)

    def generics(self):
        for rule in self.grammar.get_generics():
            assert rule.target == Generic.get(1)
            item = self.add(self.index, rule.first, [])
            item.generic_wants = self.wants

    def complete(self, right):
        for left in right.wanted_by:

            #print '[', left
            #print ']', right
            #print

            tag = left.tag
            wanted_by = left.wanted_by
            if tag.wants.has_generic:
                if not isinstance(right.tag, Type):
                    continue

                unification = tag.wants.is_super(right.tag)
                if not unification:
                    # TODO warn?
                    continue
                old, tag = tag, tag.specialise(unification)
                assert old.rule.target.is_super(tag.rule.target)
                #print old.rule.target, ':>', tag.rule.target

                if left.tag.rule.target.has_generic:
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
        if item.tag.rule.target.has_generic:
            for type_ in item.generic_wants.keys():
                self.want(item, type_)
                self.predict(type_)

            # fix edge case
            if item.start == self.index:
                self.wants_generic.append(item)

        else:
            for type_ in self.grammar.expand(item.tag.wants):
                self.want(item, type_)
                self.predict(type_)

    def predict_expr(self, tag):
        if isinstance(tag, Word):
            return
        if tag == Type.ANY or tag == Type.EXPR:
            return
        wanted_by = self.wants[tag]

        if tag in Type.EXPR._rules:
            rule = Type.EXPR._rules[tag]
        else:
            rule = Type.EXPR._rules[tag] = Rule(tag, [Type.EXPR], CoerceMacro(tag))

        item = self.add(self.index, rule.first, wanted_by)
        # nullables need a value!
        if not isinstance(rule.first, LR0) and rule.call: # is nullable
            item.rule = rule

    def process(self):
        self.generics()

        for item in self.items:
            if isinstance(item.tag, LR0):
                target = item.tag.wants
                if target.has_generic:
                    self.predict_generic(item)
                else:
                    self.predict(target)

                # nullable hack.
                # sometimes we predict a nullable that's already been completed...
                other = self.has(self.index, target)
                if other and not isinstance(other.tag, LR0) and other.rule.call: # is nullable
                    self.complete(other) # TODO optimize

            else:
                self.complete(item)

    def evaluate(self):
        for item in self.items:
            if not isinstance(item.tag, LR0):
                item.evaluate()

    def print_(self):
        print self.index
        for item in self.items:
            print item
        print


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
        # TODO Type rules
        #self.add(Type.TYPE, [Word.word(type_.name)], TypeMacro)

    def remove(self, rule):
        # TODO should this traverse the stack?
        for rule_sets in reversed(self.stack):
            rules = rule_sets[target]
            if rule in rules:
                rules.remove(rule)
                return

    def get(self, target):
        # TODO specialise target for container types.

        if isinstance(target, List) and not target.has_generic:
            # TODO Rules need to be uniqued.
            list_gen = List.get(Generic.get(1))
            matches = self.get(list_gen)
            unification = list_gen.is_super(target)
            if unification is not None:
                for m in matches:
                    yield m.specialise(unification)

        matches = []
        for rule_sets in reversed(self.stack):
            if target in rule_sets:
                matches += rule_sets[target]
        for m in matches:
            yield m

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

    def expand(self, tag):
        assert isinstance(tag, Tag)
        if isinstance(tag, Generic):
            return self.types
        return [tag]


def grammar_parse(source, grammar, debug=DEBUG):
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
    while token != Word.EOF:
        if token != Word.NL:
            if token == Word.WS:
                line += " "
            else:
                line += token.value

        if debug:
            column.print_()

        previous, column = column, Column(grammar, index + 1)
        if not column.scan(token, previous):
            msg = "Unexpected " + token.kind + " @ " + str(index)
            if token.value:
                msg += ": " + token.value
            for token in previous.wants:
                if isinstance(token, Word):
                    msg += "\nExpected: " + token.sexpr()
            msg += "\n>> " + line
            return msg
        column.process()

        if token == Word.word('{'):
            column.evaluate()
        elif token == Word.word('}'):
            column.evaluate()

        if token == Word.NL:
            line = ""

        token = lexer.lex()
        index += 1

    if debug:
        column.print_()
    key = 0, Type.PROGRAM
    if key not in column.unique:
        msg = "Unexpected EOF"
        #for token in previous.wants:
        #    if isinstance(token, Word):
        #        msg += "\nExpected: " + token.sexpr()
        #msg += "\n>> " + line
        return msg
    start = column.unique[key]
    value = start.evaluate()

    return value.sexpr()

