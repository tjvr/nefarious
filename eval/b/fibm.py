
def fib(n):
    seq = [1, 1]
    for i in range(n - 1):
        index = len(seq)
        seq.append(seq[-1] + seq[-2])
    return seq[-1]

import sys
n = int(sys.argv[1])
y = int(sys.argv[2])
out = None
for i in range(y):
    out = fib(n)
print out
