import sys
sys.path.append('./pypy/')

from .nefarious import entry_point
entry_point(sys.argv)

