
import struct

try:
    from rpython.rlib.rarithmetic import r_uint, r_int, intmask
    from rpython.rlib.objectmodel import we_are_translated
except ImportError:
    def we_are_translated(): return False
    r_uint = r_int = intmask = lambda x: x
# from rpython.rlib.rbigint import ...

from .grammar import *
from .ops import Op




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


class Block(Value):
    def __init__(self, name):
        assert isinstance(name, str)
        self.debug_name = name

        self.opcodes = []
        self.code = None

        self.is_primitive = True
        self.num_locals = 0
        self.constants = []
        self.local_names = {}
        self.local_var_names = {}

    def __repr__(self):
        return "<Block {!r}>".format(self.debug_name)

    def sexpr(self):
        return "<" + self.debug_name + ">"

    def compile(self, tree, env=None, args=None):
        if env is None:
            env = Env()

        if args:
            for name in args:
                self.local_names[name] = self._tmp()
            assert self.num_locals == len(args)

        self.compile_node(tree, env)

        self.code = b''.join(self.opcodes)
        return env

    def emit(self, opcode, a, b, c=-1):
        if (c is -1) != (opcode < HAVE_OUTPUT):
            raise ValueError("wrong number of args: " + Op.str(opcode))
        if c is -1:
            b, c = a, b
        assert Op.is_op(opcode), opcode
        index = len(self.opcodes)
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
        return index

    def backpatch(self, index, bx):
        self.opcodes[index + 0] = chr((bx >> 8) & 0xff)
        self.opcodes[index + 1] = chr(bx & 0xff)

    def move(self, dest, src):
        self.emit(Op.MOVE, dest, src, 0)

    def compile_node(self, node, env):
        if isinstance(node, Name):
            return self.get(node, env)
        elif isinstance(node, Value):
            return self.constant(node)
        elif isinstance(node, Call):
            return self.compile_call(node, env)
        elif isinstance(node, Instruction):
            return self.builtin(node, env)
        assert False, node.__class__

    def compile_call(self, call, env):
        name = call.func
        if name == PROGRAM or name == BLOCK:
            last = self.seq(call.args, env)
            self.emit(Op.RETURN, 0, last + 1, 0)
            return -1
        #elif name == QUOTE:
        #    expr, = call.args
        #    return self.quote(expr, env)
        elif name == LET:
            self.let(call.args, env)
            return -1
        elif name == VAR:
            if len(call.args) > 1:
                name, expr = call.args
                value = 1 + self.compile_node(expr, env)
            else:
                name, = call.args
                value = 0
            cell = self._tmp()
            self.emit(Op.NEW_VAR, cell, value, 0)
            self.local_names[name] = cell
            self.local_var_names[name] = None
            return -1
        elif name == SET:
            self.set(call.args, env)
            return -1
        elif name == DEFINE:
            self.define(call.args, env)
            return -1
        elif name == RETURN:
            self.return_(call.args, env)
            return -1
        else:
            return self.call(name, call.args, env)

    def none(self):
        return self.constant(None)

    def get(self, name, env):
        if name in self.local_names:
            return self.local_names[name]

        # TODO can we burn Env?
        return self.constant(env.lookup(name))

    def constant(self, value):
        n = len(self.constants)
        self.constants.append(value)
        out = self._tmp()
        self.emit(Op.LOAD_CONSTANT, n, out)
        return out

    def let(self, args, env):
        name, expr = args
        value = self.compile_node(expr, env)
        reg = self._tmp()
        self.local_names[name] = reg
        self.move(reg, value)

    def get_var(self, name, env):
        assert name in self.local_names
        is_var = name in self.local_var_names
        assert is_var
        out = self._tmp()
        self.emit(Op.GET, out, self.local_names[name], 0)
        return out

    def set_var(self, args, env):
        name, expr = args
        #is_var = name in self.local_var_names
        #assert is_var, name
        cell = self.local_names[name]
        value = self.compile_node(expr, env)
        self.emit(Op.SET, cell, value, 0)

    def return_(self, args, env):
        if len(args):
            expr, = args
            value = self.compile_node(expr, env)
            self.emit(Op.RETURN, 0, value + 1, 0)
        else:
            self.emit(Op.RETURN, 0, 0, 0)

    def quote(self, expr, env):
        self.constants.append(expr)

    def define(self, args, env):
        args = list(args)
        block = args.pop()
        name = args.pop(0)
        assert isinstance(name, Name)
        func = Block(name.name)
        env.set(name, func)
        func.compile(block, Env(env), args)

    def call(self, name, args, env):
        name = self.compile_node(name, env)
        args = [self.compile_node(arg, env) for arg in args]
        out = self._tmp()
        for value in args:
            self.emit(Op.ARG, 0, value, 0)
        self.emit(Op.CALL, out, name, 0)
        return out

    def builtin(self, node, env):
        return node.emit(self, env)

        if node.opcode < HAVE_OUTPUT:
            self.emit(node.opcode, out, node.bx, node.c)
        else:
            self.emit(node.opcode, out, node.a, node.b, node.c)

        if name == IF:
            test, te, fe = args
            test = self.compile_node(test, env)
            out = self._tmp()

            start = self.emit(Op.JUMP_UNLESS, -1, test + 1)
            tv = self.compile_node(te, env)
            self.move(out, tv)

            middle = self.emit(Op.JUMP_UNLESS, -1, 0)
            fv = self.compile_node(fe, env)
            self.move(out, fv)

            end = self.emit(Op.NOP, 0, 0)

            self.backpatch(start, middle - start + 4)
            self.backpatch(middle, end - middle + 4)

            return out

        args = [self.compile_node(arg, env) for arg in args]
        if name == ADD:
            a, b = args
            out = self._tmp()
            self.emit(Op.INT_ADD, out, a, b)
            return out
        elif name == SUB:
            a, b = args
            out = self._tmp()
            self.emit(Op.INT_SUB, out, a, b)
            return out
        elif name == LT:
            a, b = args
            out = self._tmp()
            self.emit(Op.INT_LT, out, a, b)
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


class W_Var:
    """a mutable cell"""

    def __init__(self):
        self.value = Value.NULL

    def __repr__(self):
        return "<W_Var {}>".format(hex(id(self))[-6:-2])

    def get(self):
        return self.value

    def set(self, value):
        assert isinstance(value, Value), value
        self.value = value



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
        return r_int(runpack('>h', chars))
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
        if result is not None:
            print result.sexpr()

    def execute(self):
        frame = self.frames.pop()
        while frame:
            next_ = frame.dispatch_bytecode(self.registers)
            if next_ is None: # RETURN
                if len(self.frames) == 0:
                    return
                frame = self.frames.pop()
                print
                print '--ret--'
            elif next_ != frame: # CALL
                self.frames.append(frame)
                frame = next_
                print
                print '--call--'

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

        next_instr = r_uint(intmask(self.next_instr))
        opcode = ord(code[next_instr + 3])

        print top, stack
        if opcode >= HAVE_OUTPUT:
            a = ord(code[next_instr])
            b = ord(code[next_instr + 1])
            c = ord(code[next_instr + 2])
            print 'v'+str(a), ':=', Op.str(opcode), 'v'+str(b), 'v'+str(c)
        else:
            bx = sint_16(code[next_instr:next_instr + 2])
            c = ord(code[next_instr + 2])
            if opcode == Op.LOAD_CONSTANT:
                print 'v'+str(c), ':=', Op.str(opcode), self.constants[bx].sexpr()
            else:
                print Op.str(opcode), 'v'+str(c), '+'+str(bx)
        self.next_instr += 4

        # nb. should translate into a switch()

        if opcode == Op.RETURN:
            if b == 0:
                stack[self.result] = None
            else:
                stack[self.result] = stack[top + b - 1]
            while len(stack) > top:
                stack.pop()
            return None

        elif opcode == Op.ARG:
            stack.append(stack[top + b])

        elif opcode == Op.CALL:
            out = top + a
            func = stack[top + b]

            new_top = self.top + self.size
            frame = Frame(new_top, func, out)
            new_end = new_top + frame.size
            while len(stack) < new_end:
                stack.append(None)
            return frame

        elif opcode == Op.JUMP_UNLESS:
            if c == 0:
                jump = True
            else:
                cond = stack[top + c - 1]
                assert isinstance(cond, W_Bool)
                jump = not cond.value
            if jump:
                print '==jump ' + str(bx) + ' =='
                target = intmask(next_instr) + bx
                assert target >= 0
                self.next_instr = target

        elif opcode == Op.NOP:
            pass

        elif opcode == Op.INT_ADD:
            stack[top + a] = self.INT_ADD(stack[top + b], stack[top + c])
        elif opcode == Op.INT_SUB:
            stack[top + a] = self.INT_SUB(stack[top + b], stack[top + c])
        elif opcode == Op.INT_LT:
            stack[top + a] = self.INT_LT(stack[top + b], stack[top + c])
        elif opcode == Op.MOVE:
            stack[top + a] = stack[top + b]
        elif opcode == Op.NEW_VAR:
            assert a == 0
            stack[top + a] = cell = W_Var()
            if b > 0:
                value = stack[top + b - 1]
                cell.set(value)
        elif opcode == Op.SET:
            cell = stack[top + a]
            value = stack[top + b]
            print cell, value
            assert isinstance(cell, W_Var)
            cell.set(value)
        elif opcode == Op.GET:
            cell = stack[top + b]
            assert isinstance(cell, W_Var)
            stack[top + a] = cell.get()
        elif opcode == Op.LOAD_CONSTANT:
            stack[top + c] = self.constants[bx]
        else:
            raise NotImplementedError(Op.str(opcode))
        return self
        #if jit.we_are_jitted():
        #    return next_instr


    # TODO bigints
    def INT_ADD(self, x, y):
        return W_Int(x.value + y.value)
    def INT_SUB(self, x, y):
        return W_Int(x.value - y.value)
    def INT_LT(self, x, y):
        return W_Bool.get(x.value < y.value)

