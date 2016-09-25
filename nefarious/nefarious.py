
import os
import sys

from .grammar import parse, parse_and_run




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

def run(fp, parse_only):
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
        msg = parse_and_run(source)
    os.write(1, msg)
    os.write(1, '\n')
    #mainloop(program)

def entry_point(argv):
    parse_only = False
    if argv[1] == '--parse':
        argv.pop(1)
        parse_only = True

    try:
        filename = argv[1]
    except IndexError:
        print "You must supply a filename"
        return 1

    if filename == '-':
        fp = 0
    else:
        fp = os.open(filename, os.O_RDONLY, 0777)
    run(fp, parse_only)
    return 0

def target(*args):
    return entry_point, None

if __name__ == "__main__":
    entry_point(sys.argv)

