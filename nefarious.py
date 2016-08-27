
import os
import sys

from parser import parse


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



# def get_location(pc, program, bracket_map):
#     return "%s_%s_%s" % (
#             program[:pc], program[pc], program[pc+1:]
#             )
# 
# jitdriver = JitDriver(
#     greens=['pc', 'program', 'bracket_map'],
#     reds=['tape'],
#     get_printable_location=get_location
# )


def entry_point(argv):
    return entry_point, None

def run(fp):
    source = ""
    while True:
        read = os.read(fp, 4096)
        if len(read) == 0:
            break
        source += read
    os.close(fp)
    tokens = parse(source)
    for tok in tokens:
        os.write(tok[0])
        os.write(tok[1])
        os.write('\n')
    #mainloop(program)

def entry_point(argv):
    try:
        filename = argv[1]
    except IndexError:
        print "You must supply a filename"
        return 1
    
    run(os.open(filename, os.O_RDONLY, 0777))
    return 0

def target(*args):
    return entry_point, None

if __name__ == "__main__":
    entry_point(sys.argv)

