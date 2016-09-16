# vim: tw=0
from contextlib import contextmanager
import os
from StringIO import StringIO
import sys
import unittest

from nefarious.types import *
from nefarious.grammar import parse

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
    # - Expr
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
        self.assertFalse(Type.ANY.has_generic)
        self.assertFalse(Type.EXPR.has_generic)

    def test_insert_lookup(self):
        self.assertEqual(Generic(1).insert_keys(), Type.EXPR.insert_keys())
        self.assertEqual(Generic(1).lookup_keys(), Type.ANY.lookup_keys())

    def test_insert(self):
        Int = Type.get('Int')
        self.assertEqual(Int.insert_keys(),
            [Type.ANY, Int]
        )
        self.assertEqual(List.get(Int).insert_keys(),
            [Type.ANY, List.get(Type.ANY), List.get(Int)]
        )
        self.assertEqual(List.get(Type.ANY).insert_keys(),
            [Type.ANY, List.get(Type.ANY)]
        )
        self.assertEqual(Type.ANY.insert_keys(),
            [Type.ANY]
        )
        self.assertEqual(Generic.get(1).insert_keys(),
            [Type.EXPR]
        )
        self.assertEqual(List.get(List.get(Int)).insert_keys(),
            [Type.ANY, List.get(Type.ANY), List.get(List.get(Type.ANY)), List.get(List.get(Int))]
        )

    def test_lookup(self):
        Int = Type.get('Int')
        self.assertEqual(Type.ANY.lookup_keys(),
            [Type.ANY, Type.EXPR]
        )
        self.assertEqual(Int.lookup_keys(),
            [Int, Type.EXPR]
        )
        self.assertEqual(List.get(Int).lookup_keys(),
            [List.get(Int), List.get(Type.EXPR), Type.EXPR]
        )
        self.assertEqual(
            List.get(Type.ANY).lookup_keys(),
            [List.get(Type.ANY), List.get(Type.EXPR), Type.EXPR]
        )
        self.assertEqual(
            List.get(Generic.get(1)).lookup_keys(),
            [List.get(Type.ANY), List.get(Type.EXPR), Type.EXPR]
        )

    def _accepts(self, slot, child):
        d = {}
        for key in child.insert_keys():
            d[key] = True
        for key in slot.lookup_keys():
            if key in d:
                return True
        return False

    def test_accepts(self):
        Int = Type.get('Int')
        Bool = Type.get('Bool')
        self.assertTrue(self._accepts(Int, Int))

        self.assertTrue(self._accepts(Int, Type.EXPR))
        self.assertTrue(self._accepts(Type.ANY, Int))
        self.assertTrue(self._accepts(Type.ANY, Type.EXPR))

        self.assertFalse(self._accepts(Int, Bool))
        self.assertFalse(self._accepts(Type.EXPR, Int))
        self.assertFalse(self._accepts(Int, Type.ANY))

        self.assertTrue(self._accepts(Generic(1), Int))
        self.assertTrue(self._accepts(Int, Generic(1)))
        self.assertTrue(self._accepts(List(Int), List(Int)))
        self.assertTrue(self._accepts(List(Int), List(Type.EXPR)))
        self.assertTrue(self._accepts(List(Type.ANY), List(Int)))

        self.assertFalse(self._accepts(List(Int), Int))
        self.assertFalse(self._accepts(List(Int), List(Bool)))

        self.assertTrue(self._accepts(List(Generic(1)), List(Int)))
        self.assertTrue(self._accepts(List(Int), List(Generic(1))))
        self.assertTrue(self._accepts(List(Generic(1)), List(Generic(1))))
        self.assertTrue(self._accepts(List(Generic(1)), List(Generic(2))))


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
    def test_03(self): self._parse("(goodbye)", "goodbye")
    #def test0_4(self): self._error("choose hello or goodbye") # TODO
    def test_05(self): self._parse("choose hello or hello", "(choice hello hello)")
    def test_06(self): self._parse("hello < hello", "(cmp hello hello)")
    def test_07(self): self._parse("choose hello < hello or false", "(choice (cmp hello hello) false)")
    def test_08(self): self._parse("choose (hello < hello) or false", "(choice (cmp hello hello) false)")
    def test_09(self): self._parse("hello, hello", "(list hello hello)")
    def test_10(self):
        """sometimes we predict a nullable that's already been completed"""
        self._parse("(hello, hello)", "(list hello hello)")
    def test_11(self): self._parse("false, hello < hello", "(list false (cmp hello hello))")

    def test_12(self): self._parse("hello + foo", "(+ hello (coerce <Int> foo))")
    def test_13(self): self._parse("hello + choose hello or foo", "(+ hello (choice hello (coerce <Int> foo)))")

    def test_14(self): self._parse("range hello to hello", "(range hello hello)")

