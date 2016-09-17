# vim: tw=0
from contextlib import contextmanager
import os
from StringIO import StringIO
import sys
import unittest

from nefarious.types import *
from nefarious.lex import Word
from nefarious.grammar import grammar, parse

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


class TypesTests(unittest.TestCase):

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


    def setUp(self):
        self.all_types = [
            Generic.ALPHA,
            List.get(Type.ANY),
            List.get(Generic.ALPHA),
            List.get(Type.ANY),
            List.get(List.get(Generic.ALPHA)),
            List.get(List.get(Type.get('Int'))),
            List.get(List.get(Type.get('Int'))),
        ] + grammar.scope.types

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
        for a in grammar.scope.types:
            for b in grammar.scope.types:
                self.assertEqual(bool(a.is_super(b)), self._accepts(a, b))

        for a in grammar.scope.types:
            la = List.get(a)
            for b in grammar.scope.types:
                lb = List.get(b)
                self.assertEqual(bool(la.is_super(lb)), self._accepts(la, lb))

    def test_grammar(self):
        Int = Type.get('Int')


class GrammarTests(unittest.TestCase):
    def setUp(self):
        self.all_rules = []
        for tag in grammar.scope.rule_sets:
            self.all_rules += grammar.scope.rule_sets[tag]

    def test_all(self):
        """Check every rule gets inserted under Type.ANY

        (except for Type.PROGRAM)

        """
        every_rule = list(self.all_rules)
        for program_rule in grammar.scope.rule_sets[Type.PROGRAM]:
            every_rule.remove(program_rule)

        any_rules = grammar.scope.rule_sets[Type.ANY]
        for rule in every_rule:
            if isinstance(rule.target, Word):
                continue
            self.assertIn(rule, any_rules)


# TODO move grammar into setUp()

class ParserTests(unittest.TestCase):
    # Enable stdout
    DEBUG = False

    def _execute(self, source):
        return parse(source + "\n", debug=self.DEBUG)

    def _parse(self, source, sexpr):
        # nb. debug reprs / capturing stdout is slow!
        result = self._execute(source)
        print result
        print
        print "Test input:"
        print source
        print
        print "Expected result:"
        print sexpr
        self.assertEqual(result, sexpr)

    def _error(self, source):
        result = self._execute(source)
        self.assertIn("Unexpected", result)
        self.assertIn("\n>>", result)

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
    # TODO this parses wrong, because we're not correctly unifying typevars during completion.

    #def test_05b(self): self._error("choose hello or goodbye") # TODO
    def test_06(self): self._parse("hello < hello", "(cmp hello hello)")
    def test_07(self): self._parse("choose hello < hello or false", "(choice (cmp hello hello) false)")
    def test_08(self): self._parse("choose (hello < hello) or false", "(choice (cmp hello hello) false)")

    def test_12(self): self._parse("hello + foo", "(+ hello foo)")
    def test_13(self): self._parse("hello + choose hello or foo", "(+ hello (choice hello foo))")

    def test_14(self): self._parse("range hello to hello", "(range hello hello)")

