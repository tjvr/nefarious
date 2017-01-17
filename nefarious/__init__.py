
import os
import sys
sys.path.append('./pypy/')

from .grammar import parse, parse_and_run



def run(fp, parse_only, inlining):
    source = ""
    while True:
        read = os.read(fp, 4096)
        if len(read) == 0:
            break
        source += read
    os.close(fp)
    if parse_only:
        msg = parse(source)
    else:
        msg = parse_and_run(source, inlining=inlining)
    os.write(1, msg)
    os.write(1, '\n')
    #mainloop(program)

def entry_point(argv):
    parse_only = False
    inlining = True
    try:
        while True:
            if argv[1] == '--parse':
                argv.pop(1)
                parse_only = True
            elif argv[1] == '--noinline':
                argv.pop(1)
                inlining = False
            else:
                break
        filename = argv[1]
    except IndexError:
        print "You must supply a filename"
        return 1

    if filename == '-':
        fp = 0
    else:
        fp = os.open(filename, os.O_RDONLY, 0777)
    run(fp, parse_only, inlining)
    return 0

def target(*args):
    return entry_point, None

