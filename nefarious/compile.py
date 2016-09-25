
import struct

try:
    from rpython.rlib.rarithmetic import r_uint, r_int, intmask
    from rpython.rlib.objectmodel import we_are_translated
    from rpython.rlib.rstruct.runpack import runpack
except ImportError:
    def we_are_translated(): return False
    r_uint = r_int = intmask = lambda x: x
# from rpython.rlib.rbigint import ...

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
    _ops = {}

    @staticmethod
    def str(code):
        return Op._ops[code]

    @staticmethod
    def is_op(code):
        return code in Op._ops

# No args.
Op.HALT = 1
Op.RET = 2
Op.CALL = 3
Op.JUMP_IF = 4
Op.LOAD_CONSTANT = 5

# Three args
HAVE_OUTPUT = 24
Op.MOV = 24         # MOV dest src [unused]
Op.INT_ADD = 49     # INT_ADD result x y
Op.INT_SUB = 50     # INT_SUB result x y

for key in Op.__dict__:
    if key.isalpha and key.isupper():
        value = getattr(Op, key)
        Op._ops[value] = key


class Block(Value):
    def __init__(self, name):
        assert isinstance(name, str)
        self.debug_name = name

        self.opcodes = []
        self.code = None

        # ohkayyyy. now there is *no stack*. have to invent temporaries.
        self.locals = []
        self.constants = []
        self.num_args = 0
        self.frame_size = 0 # num_args + num_locals
        # constants
        # locals

    def compile(self, tree, env=None):
        if env is None:
            env = Env(builtins)
        self.compile_node(tree, env)
        # TODO pop args
        # TODO push return value

        self.code = b''.join(self.opcodes)
        return env

    def emit(self, opcode, a, b, c=-1):
        if (c is -1) != (opcode < HAVE_OUTPUT):
            raise ValueError("wrong number of args: " + Op.str(opcode))
        if c is -1:
            b, c = a, b
        assert Op.is_op(opcode), opcode
        if opcode >= HAVE_OUTPUT:
            self.opcodes.append(chr(a & 0xff))
            self.opcodes.append(chr(b & 0xff))
            self.opcodes.append(chr(c & 0xff))
            self.opcodes.append(chr(opcode & 0xff))
        else:
            self.opcodes.append(chr((b >> 8) & 0xff))
            self.opcodes.append(chr(b & 0xff))
            self.opcodes.append(chr(c & 0xff))
            self.opcodes.append(chr(opcode & 0xff))

    def _print(self):
        print self.debug_name
        #for ins in self.instructions:
        #    print ins
        print

    def compile_node(self, node, env):
        self.emit(Op.INT_ADD, 1, 2, 3)
        self.emit(Op.INT_SUB, -256, 255, 255)
        self.emit(Op.MOV, 2, 0, 0)
        self.emit(Op.MOV, 3, 0, 0)
        self.emit(Op.RET, 12345, 1)
        self.emit(Op.RET, -12345, 1)
        self.emit(Op.HALT, 0, 0)
        return

        if isinstance(node, Name):
            self.emit(Op.STORE, node)
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
        # TODO args
        func.compile(block, Env(env))

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

#------------------------------------------------------------------------------

try:
    from rpython.rlib.jit import JitDriver, purefunction
except ImportError:
    # Dummy class for running under standard CPython
    class JitDriver(object):
        def __init__(self,**kw): pass
        def jit_merge_point(self,**kw): pass
        def can_enter_jit(self,**kw): pass
    def purefunction(f): return f

def jitpolicy(driver):
    from rpython.jit.codewriter.policy import JitPolicy
    return JitPolicy()


# For decoding 16-bit signed int
def sint_16(chars):
    if we_are_translated():
        return runpack('>h', chars)
    else:
        return struct.unpack('>h', chars)[0]


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
        self.dispatch_bytecode(self.frame.block.code, 0)

    #    stack = self.stack
    #    while True:
    #        frame = self.frame
    #        ins = frame.block.instructions[frame.index]
    #        first = ins.args[0]
    #        if ins.op == Op.LOAD:
    #            stack.append(first)
    #        elif ins.op == Op.GET:
    #            stack.append(frame.env.lookup(first))
    #        elif ins.op == Op.SET:
    #            frame.env.set(first, stack.pop())
    #        elif ins.op == Op.CALL:
    #            if isinstance(first, Builtin): # TODO separate opcodes
    #                self.call_builtin(first.name)
    #            else:
    #                assert False, first
    #        elif ins.op == Op.HALT:
    #            print self.stack.pop().sexpr()
    #            return
    #        else:
    #            assert False, ins
    #        frame.index += 1

    def handle_bytecode(self, code, next_instr):
        next_instr = self.dispatch_bytecode(code, next_instr)
        # except KeyboardInterrupt:
        # except MemoryError:
        # except rstackovf.StackOverflow as e:
        #     Note that this case catches AttributeError!
        return next_instr

    #@jit.unroll_safe
    def dispatch_bytecode(self, code, next_instr):
        #stack = self.stack
        stack = [20, 30, 40, 50]
        top = 0
        a = b = bx = c = 0
        while True:
            print '   ', stack
            next_instr = r_uint(intmask(next_instr))
            opcode = ord(code[next_instr + 3])

            if opcode >= HAVE_OUTPUT:
                a = ord(code[next_instr])
                b = ord(code[next_instr + 1])
                c = ord(code[next_instr + 2])
                print Op.str(opcode), a, b, c
            else:
                bx = sint_16(code[next_instr:next_instr + 2])
                c = ord(code[next_instr + 2])
                print Op.str(opcode), bx, c
            next_instr += 4

            if opcode == Op.HALT:
                return
            elif opcode == Op.INT_ADD:
                stack[top + a] = self.INT_ADD(stack[top + b], stack[top + c])
            elif opcode == Op.MOV:
                stack[top + a] = stack[top + b]

            # nb. translates into a switch()

            #print opcode

            #if opcode == Op.RETURN_VALUE.index:
            #    w_returnvalue = self.popvalue()
            #    block = self.unrollstack(SReturnValue.kind)
            #    self.pushvalue(w_returnvalue)   # XXX ping pong
            #    raise Return
            #elif opcode == opcodedesc.JUMP_ABSOLUTE.index:
            #    return self.jump_absolute(oparg, ec)
            #elif opcode == opcodedesc.BREAK_LOOP.index:
            #    next_instr = self.BREAK_LOOP(oparg, next_instr)

            #if jit.we_are_jitted():
            #    return next_instr
    
    def INT_ADD(self, x, y):
        # TODO bigints
        return x + y

    #@jit.unroll_safe
    def unrollstack(self, unroller_kind):
        while self.blockstack_non_empty():
            block = self.pop_block()
            if (block.handling_mask & unroller_kind) != 0:
                return block
            block.cleanupstack(self)
        self.frame_finished_execution = True  # for generators
        return None

    def unrollstack_and_jump(self, unroller):
        block = self.unrollstack(unroller.kind)
        if block is None:
            raise BytecodeCorruption("misplaced bytecode - should not return")
        return block.handle(self, unroller)

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

