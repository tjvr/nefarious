
# vim: tw=0

import os
from StringIO import StringIO
import unittest
import sys
sys.path.append('./pypy/')

import nefarious.tree
import nefarious.builtins
from nefarious.types import *
from nefarious.tree import Transform
from nefarious.builtins import *

SELF_PATH = os.path.dirname(os.path.abspath(__file__))


class NullTransform(Transform):
    def transform(self, node):
        return node._copy(self)

class CopyTests(unittest.TestCase):
    """Check copy() does the right thing."""

    def _check_children(self, instance):
        children = instance.children()
        cls_name = instance.__class__.__name__
        for name, child in instance.__dict__.items():
            if name != '_parent' and isinstance(child, Node):
                self.assertIn(child, children,
                    "{} doesn't expose child {}".format(cls_name, name)
                )
                self.assertEqual(child._parent, instance, cls_name)
        # TODO check replace_Child is defined

    def _assert_different(self, instance, clone):
        self.assertNotEqual(instance, clone)
        for a, b in zip(instance.children(), clone.children()):
            self._assert_different(a, b)

    def _check_copy(self, instance, clone):
        self.assertEqual(instance.sexpr(), clone.sexpr())
        self._assert_different(instance, clone)
        self._check_children(clone)

    def _test_class(self, cls):
        assert cls._test_cases
        for instance in cls._test_cases():
            self._check_children(instance)
            self._check_copy(instance, instance.copy())
            self._check_copy(instance, instance.copy(NullTransform()))


# Define tests declaratively

def create_test(cls):
    test_name = cls.__name__
    def _test(self):
        self._test_class(cls)
    setattr(CopyTests, "test_{}".format(test_name), _test)

def test_module_node_classes(mod):
    for name in dir(mod):
        cls = getattr(mod, name)
        if isinstance(cls, type) and issubclass(cls, Node):
            if cls in ignore_classes:
                continue
            if hasattr(cls, '_test_cases'):
                create_test(cls)
            else:
                print 'needs _test_cases:', cls.__name__

ignore_classes = {
    Node,
    Error,
    WordNode,
    Builtin,
    UnaryBuiltin,
    InfixBuiltin,
    Lambda, # TODO figure out what this should do
}

#test_module_node_classes(nefarious.tree)
test_module_node_classes(nefarious.builtins)

