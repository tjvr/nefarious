
import struct

try:
    from rpython.rlib.rarithmetic import r_uint, r_int, intmask
    from rpython.rlib.objectmodel import we_are_translated
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



builtins = {
    IF: None,
    LT: None,
    ADD: None,
    SUB: None,
}



class Op:
    _ops = {}

    @staticmethod
    def str(code):
        return Op._ops[code]

    @staticmethod
    def is_op(code):
        return code in Op._ops

# 2 args: Bx C
Op.JUMP_IF = 4
Op.LOAD_CONSTANT = 5

# 3 args: A B C
HAVE_OUTPUT = 16
Op.CALL = 16
Op.ARG = 17
Op.RET = 18
Op.MOVE = 24        # MOVE dest src _
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
        self.num_locals = 0
        self.constants = []
        self.arg_names = []
        self.frame_size = 0 # num_args + num_locals
        # constants
        # locals

    def compile(self, tree, env=None, args=None):
        if env is None:
            env = Env()

        if args:
            self.arg_names = args
            self.num_locals = max(0, len(args))

        self.compile_node(tree, env)

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

    def move(self, dest, src):
        self.emit(Op.MOVE, dest, src)

    def compile_node(self, node, env):
        if isinstance(node, Name):
            return self.get(node, env)
        elif isinstance(node, Value):
            return self.constant(node)
        elif isinstance(node, Call):
            return self.compile_call(node, env)
        assert False, node.__class__

    def get(self, name, env):
        return self.arg_names.index(name)

    def constant(self, value):
        n = len(self.constants)
        self.constants.append(value)
        out = self._tmp()
        self.emit(Op.LOAD_CONSTANT, n, out)
        return out

    def compile_call(self, call, env):
        name = call.func
        if name == PROGRAM or name == BLOCK:
            last = self.seq(call.args, env)
            self.emit(Op.RET, 0, last, 0)
            return -1
        elif name == DEFINE:
            return self.define(call.args, env)
        elif name in builtins:
            return self.builtin(name, call.args, env)
        else:
            return self.call(name, call.args, env)

    def define(self, args, env):
        args = list(args)
        block = args.pop()
        name = args.pop(0)
        assert isinstance(name, Name)
        func = Block(name.name)
        env.set(name, func)
        func.compile(block, Env(env), args)
        return -1

    def call(self, name, args, env):
        name = self.compile_node(name, env)
        args = [self.compile_node(arg, env) for arg in args]
        out = self._tmp()
        for value in args:
            self.emit(Op.ARG, 0, value)
        self.emit(Op.CALL, out, name, 0)
        return out

    def builtin(self, name, args, env):
        args = [self.compile_node(arg, env) for arg in args]
        if name == ADD:
            a, b = args
            out = self._tmp()
            self.emit(Op.INT_ADD, out, a, b)
            return out
        assert False, name

    def _tmp(self):
        n = self.num_locals
        self.num_locals += 1
        return n

    def seq(self, lines, env):
        last = 0
        for line in lines:
            last = self.compile_node(line, env)
        return last


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
        from rpython.rlib.rstruct.runpack import runpack
        return runpack('>h', chars)
    else:
        return struct.unpack('>h', chars)[0]


class Runtime: # TODO -> Thread?
    def __init__(self):
        self.registers = [None]
        self.frames = []

    def run(self, block, env):
        self.frames.append(Frame(1, block, 0))
        self.registers.extend([None] * block.num_locals)
        self.execute()
        print
        assert len(self.registers) == 1
        result = self.registers[0]
        print result

    def execute(self):
        frame = self.frames.pop()
        while frame:
            next_ = frame.dispatch_bytecode(self.registers)
            if next_ is None: # RET
                if len(self.frames) == 0:
                    return
                frame = self.frames.pop()
            elif next_ != frame: # CALL
                self.frames.append(frame)
                frame = next_

    def handle_bytecode(self, code, next_instr):
        next_instr = self.dispatch_bytecode(code, next_instr)
        # except KeyboardInterrupt:
        # except MemoryError:
        # except rstackovf.StackOverflow as e:
        #     Note that this case catches AttributeError!
        return next_instr


class Frame:
    def __init__(self, top, block, result):
        self.top = top
        self.code = block.code
        self.size = block.num_locals
        self.constants = block.constants
        self.next_instr = 0
        self.result = result

    #@jit.unroll_safe
    def dispatch_bytecode(self, stack):
        a = b = bx = c = 0
        code = self.code
        top = self.top

        print '   ', stack
        next_instr = r_uint(intmask(self.next_instr))
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
        self.next_instr += 4

        # nb. should translate into a switch()

        if opcode == Op.RET:
            stack[self.result] = stack[top + b]
            while len(stack) > top:
                stack.pop()
            return None

        elif opcode == Op.ARG:
            stack.append(stack[a])

        elif opcode == Op.CALL:
            out = top + a
            func = stack[top + b]

            new_top = self.top + self.size
            frame = Frame(new_top, func, out)
            new_end = new_top + frame.size
            while len(stack) < new_end:
                stack.append(None)
            return frame

        elif opcode == Op.INT_ADD:
            stack[top + a] = self.INT_ADD(stack[top + b], stack[top + c])
        elif opcode == Op.MOVE:
            stack[top + a] = stack[top + b]
        elif opcode == Op.LOAD_CONSTANT:
            stack[top + c] = self.constants[bx]

        return self
        #if jit.we_are_jitted():
        #    return next_instr

    def INT_ADD(self, x, y):
        # TODO bigints
        return W_Int(x.value + y.value)

