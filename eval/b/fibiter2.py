
def fib(n):
    return 1.0 if n < 2.0 else fib(n-1.0)+fib(n-2.0)

import sys
n = float(sys.argv[1])
print fib(n)

