# vim: tw=0

from contextlib import contextmanager
import os
from StringIO import StringIO
import unittest
import sys
sys.path.append('./pypy/')

from nefarious.types import *
from nefarious.lex import Word
from nefarious.grammar import *
from nefarious.grammar import parse as language_parse
del grammar

SELF_PATH = os.path.dirname(os.path.abspath(__file__))


@contextmanager
def captured_output():
    new_out, new_err = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err


class TestGrammar(unittest.TestCase):
    """Set up grammar used for Generic tests."""

    def tearDown(self):
        Call.__init__ = self.old_init

    def setUp(self):
        super(TestGrammar, self).setUp()
        self.setup_grammar()
        self.setup_types()

        # Get old Call init, too
        self.old_init = Call.__init__
        def init(self, func, args, t=None):
            self.func = func
            self.args = args
        Call.__init__ = init

    def setup_grammar(self):
        self.grammar = grammar = Grammar()

        def singleton(cls):
            return cls()

        DEFINE = Function('define')

        @singleton
        class Null(Macro):
            def build(self, values, t):
                return Word.NULL_WS
        grammar.add(Word.WS, [], Null)

        LIST = Function('list')

        @singleton
        class PairList(Macro):
            def build(self, values, t):
                return Call(LIST, [values[0], values[-1]])

        @singleton
        class ContinueList(Macro):
            def build(self, values, t):
                list_ = values[0]
                assert isinstance(list_, Call)
                assert list_.func is LIST
                list_.args.append(values[-1])
                return list_

        @singleton
        class Identity(Macro):
            def build(self, values, t):
                assert len(values) == 1
                return values[0]

        Int = Type.get('Int')
        Text = Type.get('Text')
        Bool = Type.get('Bool')

        alpha = Generic.get(1)
        grammar.add(List.get(alpha), [alpha, Word.WS, Word.word(","), Word.WS, alpha], PairList)
        grammar.add(List.get(alpha), [List.get(alpha), Word.WS, Word.word(","), Word.WS, alpha, Word.WS], ContinueList)

        @singleton
        class Parens(Macro):
            def build(self, values, t):
                return values[2]
        grammar.add(Generic.get(1), [Word.word("("), Word.WS, Generic.get(1), Word.WS, Word.word(")")], Parens)

        CHOICE = Function('choice')
        @singleton
        class Choice(Macro):
            def build(self, values, t):
                return Call(CHOICE, [values[2], values[6]])
        grammar.add(Generic.get(1), [Word.word("choose"), Word.WS, Generic.get(1), Word.WS, Word.word("or"), Word.WS, Generic.get(1)], Choice)

        CMP = Function('cmp')
        @singleton
        class Cmp(Macro):
            def build(self, values, t):
                return Call(CMP, [values[0], values[4]])
        grammar.add(Type.get('Bool'), [Generic.get(1), Word.WS, Word.word("<"), Word.WS, Generic.get(1)], Cmp)

        @singleton
        class Program(Macro):
            def build(self, values, t):
                assert isinstance(values[0], Tree)
                return values[0]
        grammar.add(Type.PROGRAM, [Type.ANY, Word.NL], Program)

        grammar.add(Int, [Word.word('hello')], Identity)
        grammar.add(Text, [Word.word('goodbye')], Identity)
        grammar.add(Bool, [Word.word('false')], Identity)

        grammar.add(Int, [Int, Word.WS, Word.word("+"), Word.WS, Int], CallMacro(Function('+'), [0, 4]))

        grammar.add(Generic.ALPHA, [Word.word('foo')], Identity)

        grammar.add(List.get(Int), [Word.word('range'), Word.WS, Int, Word.WS, Word.word('to'), Word.WS, Int], CallMacro(Function('range'), [2, 6]))

    def setup_types(self):
        self.some_types = [
            Type.get('Int'),
            Type.get('Text'),
            Type.get('Bool'),
            List.get(Type.ANY),
        ]
        self.all_types = self.some_types + [
            Generic.ALPHA,
            List.get(Type.ANY),
            List.get(Generic.ALPHA),
            List.get(List.get(Generic.ALPHA)),
            List.get(List.get(Type.get('Int'))),
            List.get(List.get(Type.get('Int'))),
        ]

    def _grammar_parse(self, source, debug=False):
        return grammar_parse(source, self.grammar, debug)


class TypesTests(TestGrammar):

    # Let's see:
    # We want to predict any production whose LHS is a subtype of `tag`.
    # That is, anything that `tag` can accept.
    # That includes:
    #
    # - `tag` itself
    # - Wild
    # - any Generic
    # - if `tag` is a container type, must search subtypes recursively.
    #
    # - if `tag` is All, or a Generic, then we predict every rule.
    #   Logically. Because a generic can accept anything!
    #
    #   -- this does raise the question of unifying non-equal Generics.
    #      Oops! I think we end up alpha-renaming though?
    #
    # What about List 'a ??

    def test_types(self):
        list_int = List.get(Type.get('Int'))
        assert Type.get('Int').is_super(Type.get('Text')) == None
        assert Type.get('Int').is_super(Type.get('Int')).values == {}
        assert list_int.is_super(List(Type.get('Int'))).values == {}
        assert Generic.get(2).is_super(Type.get('Int')).values == {2: Type.get('Int')}
        assert List.get(Generic.get(1)).is_super(List.get(List.get(Type.get('Int')))).values == {1: List.get(Type.get('Int'))}
        assert List.get(Generic.get(1)) == List.get(Generic.get(1))

    def test_has_generic(self):
        self.assertTrue(Generic(1).has_generic)
        self.assertTrue(List(Generic(1)).has_generic)
        self.assertFalse(Type.get('Int').has_generic)
        self.assertFalse(List(Type.get('Int')).has_generic)
        self.assertFalse(Type.ANY.has_generic)

    def test_insert(self):
        Int = Type.get('Int')
        self.assertEqual(Int.supertypes(),
            [Type.ANY, Int]
        )
        self.assertEqual(List.get(Int).supertypes(),
            [Type.ANY, List.get(Type.ANY), List.get(Int)]
        )
        self.assertEqual(List.get(Type.ANY).supertypes(),
            [Type.ANY, List.get(Type.ANY)]
        )
        self.assertEqual(Type.ANY.supertypes(),
            [Type.ANY]
        )
        self.assertEqual(Type.PROGRAM.supertypes(),
            [Type.PROGRAM]
        )
        self.assertEqual(Generic.get(1).supertypes(),
            [Type.ANY, Generic.ALPHA]
        )
        self.assertEqual(List.get(Int).supertypes(),
            [Type.ANY, List.get(Type.ANY), List.get(Int)]
        )
        self.assertEqual(List.get(List.get(Int)).supertypes(),
            [Type.ANY, List.get(Type.ANY), List.get(List.get(Type.ANY)), List.get(List.get(Int))]
        )
        self.assertEqual(List.get(Generic.ALPHA).supertypes(),
            [Type.ANY, List.get(Type.ANY), List.get(Generic.ALPHA)]
        )

    def test_insert_all(self):
        for type_ in self.all_types:
            self.assertIn(Type.ANY, type_.supertypes())

    def test_lookup(self):
        Int = Type.get('Int')
        self.assertEqual(List.get(Int).subtypes(),
            [List.get(Int), List.get(Generic.ALPHA), Generic.ALPHA]
        )
        self.assertEqual(Type.ANY.subtypes(),
            [Type.ANY]
        )
        self.assertEqual(Type.PROGRAM.subtypes(),
            [Type.PROGRAM]
        )
        self.assertEqual(Int.subtypes(),
            [Int, Generic.ALPHA]
        )
        self.assertEqual(List.get(Type.ANY).subtypes(),
            [List.get(Type.ANY), Generic.ALPHA]
        )
        self.assertEqual(Generic.ALPHA.subtypes(),
            [Type.ANY, Generic.ALPHA]
        )
        self.assertEqual(List.get(Generic.ALPHA).subtypes(),
            [List.get(Type.ANY), List.get(Generic.ALPHA), Generic.ALPHA]
            # [List.get(Type.ANY), List.get(Generic.ALPHA), Generic.BETA] # TODO ?
        )

    def test_lookup_all(self):
        for type_ in self.all_types:
            self.assertIn(Generic.ALPHA, type_.subtypes())

    def _accepts(self, slot, child):
        d = {}
        for key in child.supertypes():
            d[key] = True
        for key in slot.subtypes():
            if key in d:
                return True
        return False

    def _does_accept(self, slot, child, fits):
        msg = "{} {} {}".format(slot, "should unify" if fits else "should not unify", child)
        self.assertEqual(bool(slot.is_super(child)), fits, msg)
        msg = "{} {} {}".format(slot, "should accept" if fits else "should not accept", child)
        self.assertEqual(self._accepts(slot, child), fits, msg)

    def test_accepts(self):
        Int = Type.get('Int')
        Bool = Type.get('Bool')
        self._does_accept(Int, Int, True)

        self._does_accept(Int, Generic.ALPHA, True)
        self._does_accept(Type.ANY, Int, True)
        self._does_accept(Type.ANY, Generic.ALPHA, True)

        self._does_accept(Int, Bool, False)
        self._does_accept(Int, Type.ANY, False)

        self._does_accept(Generic.ALPHA, Int, True)
        self._does_accept(Int, Generic(1), True)
        self._does_accept(List(Int), List(Int), True)
        self._does_accept(List(Int), List(Generic.ALPHA), True)
        self._does_accept(List(Type.ANY), List(Int), True)

        self._does_accept(List(Int), Int, False)
        self._does_accept(List(Int), List(Bool), False)

        self._does_accept(List(Generic(1)), List(Int), True)
        self._does_accept(List(Int), List(Generic(1)), True)
        self._does_accept(List(Generic(1)), List(Generic(1)), True)
        self._does_accept(List(Generic(1)), List(Generic(2)), True)

        self._does_accept(Type.ANY, List(Generic(1)), True)

    def test_accepts_all(self):
        for a in self.some_types:
            for b in self.some_types:
                self.assertEqual(bool(a.is_super(b)), self._accepts(a, b))

        for a in self.some_types:
            la = List.get(a)
            for b in self.some_types:
                lb = List.get(b)
                self.assertEqual(bool(la.is_super(lb)), self._accepts(la, lb))

    def test_specialise(self):
        list_alpha = List.get(Generic.ALPHA)
        list_int = List.get(Type.get('Int'))
        unification = list_alpha.is_super(list_int)
        self.assertEqual(list_alpha.specialise(unification), list_int)


class GrammarTests(TestGrammar):
    def setUp(self):
        super(GrammarTests, self).setUp()
        self.all_rules = []
        for tag in self.grammar.scope.rule_sets:
            self.all_rules += self.grammar.scope.rule_sets[tag]

    def test_all(self):
        """Check every rule gets inserted under Type.ANY

        (except for Type.PROGRAM)

        """
        every_rule = list(self.all_rules)
        for program_rule in self.grammar.scope.rule_sets[Type.PROGRAM]:
            every_rule.remove(program_rule)

        any_rules = self.grammar.scope.rule_sets[Type.ANY]
        for rule in every_rule:
            if isinstance(rule.target, Word):
                continue
            self.assertIn(rule, any_rules)


from nefarious.grammar import grammar

class BaseParser(unittest.TestCase):
    # Enable stdout of columns
    DEBUG = False

    def setUp(self):
        super(BaseParser, self).setUp()
        # Recover from previous failure
        while len(grammar.stack) > 1:
            grammar.restore()

        # Isolate test grammars
        grammar.save()

    def tearDown(self):
        assert len(grammar.stack) == 2
        grammar.restore()

    def _execute(self, source):
        result = self._grammar_parse(source + "\n", debug=self.DEBUG)
        if isinstance(result, Error):
            return result.message
        if isinstance(result, Tree):
            result = result.sexpr()
        return result

    def _parse(self, source, sexpr):
        # nb. debug reprs / capturing stdout is slow!
        result = self._execute(source)
        result = result.replace("\n ", " ").replace("\n", " ").replace("  ", " ").replace("  ", " ")
        print result
        print
        print "Test input:"
        print source
        print
        print "Expected result:"
        print sexpr
        self.assertEqual(result, sexpr)

    def _success(self, source):
        result = self._execute(source)
        self.assertNotIn("Unexpected", result)
        self.assertNotIn("\n>>", result)
        self.assertEqual(result[0], "{")

    def _error(self, source):
        result = self._execute(source)
        self.assertIn("Unexpected", result)
        self.assertIn("\n>>", result)


class ParserTests(TestGrammar, BaseParser):
    DEBUG = False

    def test_00(self): self._parse("hello + hello", "(+ hello hello)")
    def test_01(self): self._parse("hello", "hello")
    def test_02(self): self._parse("(hello)", "hello")
    def test_03(self): self._parse("choose hello or hello", "(choice hello hello)")
    def test_04(self): self._parse("(goodbye)", "goodbye")
    def test_04b(self): self._parse("hello, hello", "(list hello hello)")
    def test_04c(self):
        """sometimes we predict a nullable that's already been completed"""
        self._parse("(hello, hello)", "(list hello hello)")

    def test_05(self): self._parse("false, hello < hello", "(list false (cmp hello hello))")

    def test_06(self): self._parse("hello < hello", "(cmp hello hello)")
    def test_07(self): self._parse("choose hello < hello or false", "(choice (cmp hello hello) false)")
    def test_08(self): self._parse("choose (hello < hello) or false", "(choice (cmp hello hello) false)")

    def test_12(self): self._parse("hello + foo", "(+ hello foo)")
    def test_13(self): self._parse("hello + choose hello or foo", "(+ hello (choice hello foo))")

    def test_14(self): self._parse("range hello to hello", "(range hello hello)")

    def test_15(self): self._error("hello + (choose hello or goodbye)")
    def test_16(self): self._error("choose hello or goodbye")


class LanguageTests(BaseParser):

    def _grammar_parse(self, source, debug):
        return language_parse(source, debug)

    def test_00(self): self._success("define fib { 123 }")
    def test_01(self): self._success("define fib { 123 } \n 123")
    def test_02(self): self._error("define fib n { n }")
    def test_02(self): self._success("define fib Int:n { n }")
    def test_03(self): self._error("define fib Int:n { n } n")

    def test_04(self):
        self._parse("""
        define fib Int:n {
            n
            fib 123
        }
        fib 123
        """, "{ (define fib_Int n { n (fib_Int 123) }) (fib_Int 123) }")

    def test_04b(self):
        self._parse(""" define fib Int:n { n
            fib 123 }
        fib 123
        """, "{ (define fib_Int n { n (fib_Int 123) }) (fib_Int 123) }")

    def test_05(self):
        self._parse("""
        let y = 123
        y
        """, "{ (let y 123) y }")

    def test_06(self):
        self._parse("""
        let foo bar = 2
        foo bar
        """, "{ (let foo_bar 2) foo_bar }")

    def test_07(self):
        self._success("let foo2 = 123")
        self._error("let 4ducks = 123")

    def test_08(self):
        self._success("define foo { }")

    def test_08b(self):
        self._success("define foo {}")

    def test_09(self):
        self._success("""
        1
        2
        """)
        self._error("""
        1 2
        """)

    def test_10(self):
        self._parse("[1 2 3]", "{ (list 1 2 3) }")
        self._parse("""
        [
        1 2 3
        ]
        """, "{ (list 1 2 3) }")

    def test_11(self):
        self._parse("[:x 1 :y 2 :z 3]", "{ [:x 1 :y 2 :z 3] }")
        self._parse("""
        [
            :x 1
            :y 2
            :z 3
        ]
        """, "{ [:x 1 :y 2 :z 3] }")

