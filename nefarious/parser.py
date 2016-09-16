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
            # TODO pass item.tag into build()

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

        if isinstance(tag, LR0):
            for type_ in tag.wants.lookup_keys():
                if type_ in self.wants:
                    self.wants[type_].append(item)
                else:
                    self.wants[type_] = [item]
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
        generic_wants = self.wants if tag.has_generic else None
        for type_ in tag.lookup_keys():
            self._predict(type_, generic_wants)

    def _predict(self, tag, generic_wants=None):
        wanted_by = self.wants[tag]

        for rule in self.grammar.get(tag):
            item = self.add(self.index, rule.first, wanted_by)
            # nullables need a value!
            if not isinstance(rule.first, LR0) and rule.call: # is nullable
                item.rule = rule
            item.generic_wants = generic_wants

        return

    def complete(self, right):
        for left in right.wanted_by:
            self.complete_once(left, right)
        right.wanted_by = [] # GC!

    def complete_once(self, left, right):
        print '[', left
        print ']', right

        lr0 = left.tag
        tag = left.tag.wants
        wanted_by = left.wanted_by
        generic_wants = left.generic_wants
        if tag.has_generic:
            unification = tag.is_super(right.tag)
            if not unification:
                # TODO warn?
                return

            old, lr0 = lr0, lr0.specialise(unification)
            assert old.rule.target.is_super(lr0.rule.target)
            #print old.rule.target, ':>', tag.rule.target

            if old.rule.target.has_generic:
                new_target = lr0.rule.target
                #if left.generic_wants is None:
                #    import pdb; pdb.set_trace()
                if new_target not in left.generic_wants: # TODO *_keys
                    # TODO warn?
                    return
                wanted_by = left.generic_wants[new_target]
                generic_wants = None

        # assert other.tag.wants == item.tag
        new = self.add(left.start, lr0.advance, wanted_by)
        new.add_derivation(left, right, lr0.rule)
        new.generic_wants = generic_wants

        print ' ', new
        print

    def process(self):
        for item in self.items:
            if isinstance(item.tag, LR0):
                tag = item.tag.wants
                self.predict(tag)

                # sometimes we predict a nullable that's already been completed
                if not isinstance(tag, Word) and self.grammar.is_nullable(tag):
                    # TODO: check, has `other` already been processed?
                    other = self.has(self.index, tag)
                    self.complete_once(item, other)

            else:
                self.complete(item)
        self.print_()

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
        self.scope = Scope()
        self.stack = [self.scope]
        self.highest_priority = 0

    def save(self):
        assert self.stack[-1] is self.scope
        self.scope = Scope()
        self.stack.append(self.scope)
        assert self.stack[-1] is self.scope

    def restore(self):
        assert self.stack[-1] is self.scope
        self.stack.pop()
        self.scope = self.stack[-1]
        assert self.stack[-1] is self.scope

    # Rules

    def add(self, target, symbols, call=None):
        rule = Rule(target, symbols, call)
        self.highest_priority += 1
        rule.priority = self.highest_priority

        for target in rule.target.insert_keys():
            self.scope.add(target, rule)

    def remove(self, rule):
        for scope in reversed(self.stack):
            if scope.remove(rule):
                return

    def get(self, target):
        for scope in reversed(self.stack):
            if target in scope.rule_sets:
                for rule in scope.rule_sets[target]:
                    yield rule

        # # specialise target for container types. (I think?)
        # if isinstance(target, List) and not target.has_generic:
        #     # TODO rewrite
        #     list_gen = List.get(Generic.get(1))
        #     matches = self.get(list_gen)
        #     unification = list_gen.is_super(target)
        #     if unification is not None:
        #         for m in matches:
        #             yield m.specialise(unification)

        # matches = []
        # for scope in reversed(self.stack):
        #     if target in scope.rule_sets:
        #         matches += scope.rule_sets[target]
        # for m in matches:
        #     yield m

    def is_nullable(self, target):
        for scope in reversed(self.stack):
            if target in scope.nullables:
                return True
        return False

    def generics(self):
        for scope in reversed(self.stack):
            for rule in scope.generics:
                yield rule

    # Types

    def add_type(self, type_):
        self.scope.types.append(type_)
        # TODO Type rules
        #self.add(Type.TYPE, [Word.word(type_.name)], TypeMacro)

    def expand(self, tag):
        assert isinstance(tag, Tag)
        if isinstance(tag, Generic):
            return self.all_types()
        return [tag]

    def all_types(self):
        types = []
        for scope in self.stack:
            types.extend(scope.types)
        return types


class Scope:
    def __init__(self):
        self.rule_sets = {}
        self.nullables = {}
        self.types = []

    def add(self, target, rule):
        if target not in self.rule_sets:
            self.rule_sets[target] = []
        self.rule_sets[target].append(rule)

        if len(rule.symbols) == 0:
            self.nullables[target] = None

    def remove(self, rule):
        if rule.target in self.rule_sets:
            rules = self.rule_sets[rule.target]
            try:
                rules.remove(rule)
                return True
            except IndexError:
                pass
        return False


def grammar_parse(source, grammar, debug=DEBUG):
    lexer = Lexer(source)

    column = Column(grammar, 0)
    column.wants[Type.PROGRAM] = []
    column.predict(Type.PROGRAM)
    column.process()

    #grammar.save()

    token = lexer.lex()
    index = 0
    line = ""
    previous = None
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
        if previous:
            for token in previous.wants:
                if isinstance(token, Word):
                    msg += "\nExpected: " + token.sexpr()
            msg += "\n>> " + line
        return msg
    start = column.unique[key]
    value = start.evaluate()

    return value.sexpr()

