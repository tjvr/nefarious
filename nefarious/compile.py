from .grammar import *

def run(bytecode):
    print 'run'
    print bytecode

class Env:
    def __init__(self, parent=None):
        self.parent = parent
        self.names = {}

    def lookup(self, name):
        assert isinstance(name, Name)
        if name in self.names:
            return self.names[name]
        if self.parent:
            return self.parent.lookup(name)
        raise AttributeError("name '" + name.name + "' not found in env")

    def set(self, name, value):
        assert isinstance(name, Name)
        self.names[name] = value

class Builtin(Value):
    def __init__(self, name):
        assert isinstance(name, Name)
        self.name = name
        self.debug_name = name.name

builtins = Env()
builtins.set(IF, Builtin(IF))
builtins.set(LT, Builtin(LT))
builtins.set(ADD, Builtin(ADD))
builtins.set(SUB, Builtin(SUB))



class Op:
    def __init__(self, name):
        self.name = name
Op.GET = Op('get') # lookup Name in env and push
Op.SET = Op('set')  # pop stack and set name in env
Op.LOAD = Op('load') # push literal Value pointer onto stack
Op.CALL = Op('call')
Op.RET = Op('ret')
Op.HALT = Op('halt')

class Instruction:
    def __init__(self, op, args):
        assert isinstance(op, Op)
        assert isinstance(args, list)
        self.op = op
        self.args = args

    def __repr__(self):
        if self.op == Op.GET or self.op == Op.SET:
            inner = '"' + self.args[0].name + '"'
        elif self.op == Op.CALL:
            inner = '"' + self.args[0].debug_name + '"'
        else:
            inner = " ".join([str(a) for a in self.args])
        return "<" + self.op.name.upper() + " " + inner + ">"


class Block(Value):
    def __init__(self, name):
        assert isinstance(name, str)
        self.debug_name = name
        self.instructions = []

    def compile(self, tree, env=None, args=None):
        if env is None:
            env = Env(builtins)
        if args:
            self.get_args(args)
        self.compile_node(tree, env)
        return env

    def _print(self):
        print self.debug_name
        for ins in self.instructions:
            print ins
        print

    def emit(self, op, *args):
        ins = Instruction(op, list(args))
        self.instructions.append(ins)

    def get_args(self, args):
        for arg in reversed(args):
            self.emit(Op.SET, arg)

    def compile_node(self, node, env):
        if isinstance(node, Name):
            self.emit(Op.GET, node)
        elif isinstance(node, Value):
            self.emit(Op.LOAD, node)
        elif isinstance(node, Call):
            self.compile_call(node, env)
        else:
            assert False, node.__class__

    def compile_call(self, call, env):
        name = call.func
        if name == PROGRAM or name == BLOCK:
            self.seq(call.args, env)
            self.emit(Op.HALT, None)
        elif name == DEFINE:
            self.define(call.args, env)
        else:
            # TODO allow dynamic calls?
            self.call(name, call.args, env)

    def define(self, args, env):
        args = list(args)
        block = args.pop()
        name = args.pop(0)
        assert isinstance(name, Name)
        func = Block(name.name)
        env.set(name, func)
        func.compile(block, Env(env), args)

    def call(self, name, args, env):
        func = env.lookup(name)
        assert isinstance(func, Block) or isinstance(func, Builtin)
        for arg in args:
            self.compile_node(arg, env)
        self.emit(Op.CALL, func)

    def seq(self, lines, env):
        for line in lines:
            self.compile_node(line, env)


class Closure:
    def __init__(self, block, env):
        self.block = block
        self.env = env


class Runtime: # TODO -> Thread?
    def __init__(self):
        self.calls = []
        self.frame = None
        self.stack = []

    def run(self, block, env):
        self.frame = Frame(block, env)
        self.calls.append(self.frame)
        self.execute()

    def execute(self):
        stack = self.stack
        while True:
            frame = self.frame
            ins = frame.block.instructions[frame.index]
            first = ins.args[0]
            if ins.op == Op.LOAD:
                stack.append(first)
            elif ins.op == Op.GET:
                stack.append(frame.env.lookup(first))
            elif ins.op == Op.SET:
                frame.env.set(first, stack.pop())
            elif ins.op == Op.CALL:
                if isinstance(first, Builtin): # TODO separate opcodes
                    self.call_builtin(first.name)
                else:
                    assert False, first
            elif ins.op == Op.HALT:
                print self.stack.pop().sexpr()
                return
            else:
                assert False, ins
            frame.index += 1

    def call_builtin(self, name):
        if name == ADD:
            b, a = self.stack.pop(), self.stack.pop()
            assert isinstance(a, W_Int)
            assert isinstance(b, W_Int)
            result = W_Int(a.value + b.value)
            self.stack.append(result)
        else:
            assert False


class Frame:
    def __init__(self, block, env):
        assert isinstance(block, Block)
        assert isinstance(env, Env)
        self.block = block
        self.env = env
        self.index = 0

