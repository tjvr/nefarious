#import sys
#sys.setrecursionlimit(2000)

from .types import *
from .lex import Word, Lexer


DEBUG = False

class Rule:
    def __init__(self, target, symbols, call):
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
        from .grammar import Macro
        assert isinstance(call, Macro)
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
        rule.priority = self.priority # this is important.
        # however it surprised me that I'd remembered to do this!
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
    def __init__(self, start, tag):
        assert isinstance(tag, Tag), tag
        self.tag = tag
        assert isinstance(start, Column), start
        self.start = start
        # TODO cache wanted_by
        # TODO for generic LHSes, cache (a subset of?) column.wants

        # derivation
        self.left = None
        self.right = None
        self.rule = None

        # evaluation
        self.inside = False
        self.value = None
        self.children = None

    def add_derivation(self, left, right, rule):
        if self.rule and self.rule.priority >= rule.priority:
            return
        self.left = left
        self.right = right
        self.rule = rule

    def __repr__(self):
        return "<Item: {!r}, {!r})>".format(self.start.index, self.tag)

    def evaluate_children(self, stack):
        # nb. We don't cache children for intermediate nodes; we only cache the
        # value of completed nodes. So we-ll re-do building the list. This is
        # fine, because otherwise we'd end up copying the list anyway.
        if isinstance(self.tag, LR0) and self.tag.dot == 0:
            return []

        if self.children is not None:
            return list(self.children) # copy

        item = self
        subs = []
        while item.left:
            subs.append(item)
            item = item.left

        self.children = children = []
        for item in reversed(subs):
            child = item.right.evaluate(stack)
            assert child is not None, "item RHS evaluated to None"
            children.append(child)

        return children

    def evaluate(self, stack):
        if self.value is not None:
            return self.value
        stack.append(self)
        rule = self.rule
        if not rule: # token
            return self.value

        children = self.evaluate_children(stack)

        value = rule.call.build(children, rule.target)

        self.value = value
        assert stack.pop() == self
        return value

    def eval_enter(self):
        assert self.inside == False

        children = self.evaluate_children([])
        while len(children) < len(self.rule.symbols):
            children.append(None)

        self.rule.call.enter(children, self.rule.target)

    def eval_exit(self):
        assert self.inside == True
        self.inside = False

        children = self.evaluate_children([])
        while len(children) < len(self.rule.symbols):
            children.append(None)

        self.rule.call.exit(children, self.rule.target)


class Column:
    def __init__(self, grammar, index):
        self.grammar = grammar
        self.index = index
        self.items = []
        self.unique = {}
        self.wants = {}

    def has(self, start, tag):
        assert isinstance(start, Column)
        key = start, tag
        if key in self.unique:
            return self.unique[key]

    def add(self, start, tag):
        assert isinstance(start, Column)
        key = start, tag
        if key in self.unique:
            return self.unique[key]

        item = self.unique[key] = Item(start, tag)
        self.items.append(item)

        if isinstance(tag, LR0):
            # Remember, we predict anything that's a *subtype* of tag.wants.
            for type_ in tag.wants.subtypes():
                if type_ in self.wants:
                    wanted_by = self.wants[type_]
                else:
                    wanted_by = self.wants[type_] = {}
                wanted_by[item] = None

        return item

    def scan(self, word, previous):
        assert isinstance(word, Word)
        assert len(self.items) == 0
        if word.has_value:
            if word in previous.wants:
                item = self.add(previous, word)
                item.value = word
            token = Word.get(word.kind)
        else:
            token = word
        if token in previous.wants:
            item = self.add(previous, token)
            item.value = word
        if token == Word.WS:
            item = self.add(previous, Word.WS_NOT_NULL)
            item.value = word
        return len(self.items) > 0

    def predict(self, tag):
        # Look for items that target any *subtype* of tag.

        for type_ in tag.subtypes():
            self._predict(type_)

    def _predict(self, tag):
        for rule in self.grammar.get(tag):
            item = self.add(self, rule.first)

            # nullables need a value!
            if not isinstance(rule.first, LR0) and rule.call: # is nullable
                item.rule = rule

    def complete(self, right):
        # Look for items that want any *supertype* of right.

        wants = right.start.wants

        for tag in right.tag.supertypes():
            for left in wants.get(tag, {}):
                self._complete(left, right)

    def _complete(self, left, right):
        lr0 = left.tag
        if lr0.wants.has_generic:
            # unify generic
            unification = lr0.wants.is_super(right.tag)
            if not unification:
                return

            # specialise the rule, including its target
            old, lr0 = lr0, lr0.specialise(unification)

            if old.rule.target.has_generic:
                # after specialising, make sure the new rule can itself be
                # completed! (that is, somebody wants the specialised target).
                for tag in lr0.rule.target.supertypes():
                    if tag in left.start.wants:
                        break
                else:
                    return

        new = self.add(left.start, lr0.advance)
        assert right is not None
        new.add_derivation(left, right, lr0.rule)
        if right.tag == Type.BLOCK:
            new.inside = True

    def process(self):
        for item in self.items:
            if isinstance(item.tag, LR0):
                self.predict(item.tag.wants)
            else:
                self.complete(item)

    def evaluate(self):
        for item in self.items:
            if not isinstance(item.tag, LR0): # complete
                item.evaluate([])

    def eval_enter(self):
        if Type.BLOCK not in self.wants:
            # Unexpected Block ??
            raise ValueError()

        for item in self.wants[Type.BLOCK]:
            assert isinstance(item.tag, LR0)
            assert item.tag.wants == Type.BLOCK
            item.eval_enter()

    def eval_exit(self):
        for item in self.items:
            if item.inside:
                item.eval_exit()

    def print_(self):
        print self.index
        for item in self.items:
            print item
        print
        #from pprint import pprint
        #pprint(dict((k, list(v)) for k, v in self.wants.items()))
        #print


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

    def add(self, target, symbols, call):
        rule = Rule(target, symbols, call)
        self.highest_priority += 1
        rule.priority = self.highest_priority

        for target in rule.target.supertypes():
            self.scope.add(target, rule)
        return rule

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


class Scope:
    def __init__(self):
        self.rule_sets = {}
        self.nullables = {}

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

    first = column = Column(grammar, 0)
    column.wants[Type.PROGRAM] = {}
    column.predict(Type.PROGRAM)
    column.process()

    #grammar.save()

    token = lexer.lex()
    index = 0
    line = ""
    lineno = 1
    previous = None
    while token != Word.EOF:
        if token == Word.NL:
            lineno += 1

        if token != Word.NL:
            if token == Word.WS:
                line += " "
            else:
                line += token.value

        if debug:
            column.print_()

        if token == Word.ENTER: # { -> start of block
            try:
                column.eval_enter()
            except ValueError:
                msg = "Unexpected BLOCK on line " + str(lineno)
                msg += "\n>> " + line
                return Error(msg)

        if token == Word.NL: # end of line
            line = ""
            # Evaluate things here, so macros take effect
            column.evaluate()

        previous, column = column, Column(grammar, index + 1)
        if not column.scan(token, previous):
            msg = "Unexpected " + token.kind + " on line " + str(lineno)
            if token.value:
                msg += ": " + token.value
            for token in previous.wants:
                if isinstance(token, Word):
                    msg += "\nExpected: " + token.sexpr()
            msg += "\n>> " + line
            return Error(msg)
        column.process()

        if token == Word.EXIT: # } -> end of block
            column.eval_exit()

        token = lexer.lex()
        index += 1

    if debug:
        column.print_()
    key = first, Type.PROGRAM
    if key not in column.unique:
        msg = "Unexpected EOF"
        if previous:
            for token in previous.wants:
                if isinstance(token, Word):
                    msg += "\nExpected: " + token.sexpr()
            msg += "\n>> " + line
        return Error(msg)
    start = column.unique[key]
    value = start.evaluate([])

    return value

