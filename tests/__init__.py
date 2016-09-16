# vim: tw=0
from contextlib import contextmanager
import os
from StringIO import StringIO
import sys
import unittest

from nefarious.parser import *

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


# TODO move grammar into setUp()

class ParserTests(unittest.TestCase):
    def _parse(self, source, sexpr):
        # nb. debug reprs / capturing stdout is slow!
        result = parse(source + "\n", debug=True)
        print result
        print
        print "Test input:"
        print source
        print
        print "Expected result:"
        print sexpr
        self.assertEqual(result, sexpr)

    def _error(self, source):
        result = parse(source + "\n", debug=True)
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

    # TODO: fix expr
    #def test_12(self): self._parse("false, foo", "(list false (coerce <Bool> foo))")
