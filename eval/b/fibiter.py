
def fib(n):
    return 1 if n < 2 else fib(n-1)+fib(n-2)

import sys
n = int(sys.argv[1])
print fib(n)

