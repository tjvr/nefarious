
from .grammar import *


builtins = {
    IF: None,
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
Op.NOP = 1
Op.JUMP_IF = 4
Op.JUMP_UNLESS = 5

Op.LOAD_CONSTANT = 7

# TODO syscalls
Op.SYSARG = 8      # SYS _ arg
Op.SYSCALL = 9      # SYS op _


#-------------------------------------------

# 3 args: A B C
HAVE_OUTPUT = 16
Op.CALL = 16
Op.ARG = 17
Op.RETURN = 18

Op.NEW_VAR = 19
Op.GET = 20
Op.SET = 21

Op.MOVE = 24        # MOVE dest src _
Op.INT_ADD = 49     # INT_ADD result x y
Op.INT_SUB = 50     # INT_SUB result x y
Op.INT_LT = 51      # INT_LT _ x y

for key in Op.__dict__:
    if key.isalpha and key.isupper():
        value = getattr(Op, key)
        if value in Op._ops:
            raise ValueError, "duplicate opcode " + key
        Op._ops[value] = key

