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
    def test_types(self):
        list_int = List.get(Type.get('Int'))
        assert Type.get('Int').is_super(Type.get('Text')) == None
        assert Type.get('Int').is_super(Type.get('Int')).values == {}
        assert list_int.is_super(List(Type.get('Int'))).values == {}
        assert Generic.get(2).is_super(Type.get('Int')).values == {2: Type.get('Int')}
        assert List.get(Generic.get(1)).is_super(List.get(List.get(Type.get('Int')))).values == {1: List.get(Type.get('Int'))}
        assert List.get(Generic.get(1)) == List.get(Generic.get(1))


# TODO move grammar into setUp()

class ParserTests(unittest.TestCase):
    def _execute(self, source):
        return parse(source + "\n", debug=True)

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

    def test_1(self): self._parse("hello", "hello")
    def test_2(self): self._parse("(hello)", "hello")
    def test_3(self): self._parse("(goodbye)", "goodbye")
    #def test_4(self): self._error("choose hello or goodbye") # TODO
    def test_5(self): self._parse("choose hello or hello", "(choice hello hello)")
    def test_6(self): self._parse("hello < hello", "(cmp hello hello)")
    def test_7(self): self._parse("choose hello < hello or false", "(choice (cmp hello hello) false)")
    def test_8(self): self._parse("choose (hello < hello) or false", "(choice (cmp hello hello) false)")
    def test_9(self): self._parse("hello, hello", "(list hello hello)")
    def test_10(self): self._parse("(hello, hello)", "(list hello hello)")
    def test_11(self): self._parse("false, hello < hello", "(list false (cmp hello hello))")

    def test_12(self): self._parse("hello + foo", "(+ hello (coerce <Int> foo))")
    def test_13(self): self._parse("hello + choose hello or foo", "(+ hello (choice hello (coerce <Int> foo)))")

