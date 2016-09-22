from .grammar import *

def run(bytecode):
    print 'run'
    print bytecode

def compile(node):
    print repr(node)
    if isinstance(node, Call):
        print node.func
        return
    assert False, node

