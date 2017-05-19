#!/usr/bin/python3

import os
import sys
import subprocess



class RPythonError(Exception):
    def __init__(self, msg):
        assert isinstance(msg, str)
        self.msg = msg


def time_cmd(args):
    p = subprocess.Popen(['/usr/bin/time', '-f%U'] + args, cwd='b/',
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timing = p.stderr.read().strip()
    sys.stderr.write(p.stdout.read().decode('utf-8').split('\n')[-1])
    #assert p.returncode == 0, p.returncode
    try:
        user = float(timing)
    except ValueError:
        raise RPythonError(timing.decode('utf-8'))
    cmd = ' '.join(args)
    sys.stderr.write(" ".join(args) + " => " + str(user) + "\n")
    sys.stderr.flush()
    #print('time {cmd} --> {user}s'.format(**locals()))
    return user

def mean(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)

def benchmark(exe, args, benchmark, extra):
    return mean([
        time_cmd([exe] + args + [benchmark] + extra) for i in range(1 if TEST else 3)
    ])


def please(which, bench, *extra):
    options, ext = executables[which]
    args = options.split(' ')
    exe = args.pop(0)

    name = bench + ext
    if 'nfs' in exe:
        assert os.path.exists(os.path.join('b/', name)), name

    # name, bench, options, result, max, min
    average = benchmark(exe, args, name, list(extra))
    print(",".join((which, bench, " ".join(extra), "%.3f" % average)))
    sys.stdout.flush()
    #, str(maxval), str(minval))))

benchmarks = [
    ('spectralnorm', 5500),
    ('fibm', 40, 1000000),
    ('nbody', 5000000),
    ('binary', 20),
    #('fibiter', 40),
    ('fibiter2', 40),
    ('fibm', 40, 1000000),
]
benchmarks2 = [
    ('binary', 12),
    ('fibiter2', 31),
    ('fibm', 40, 1000000),
    ('nbody', 500000),
    ('spectralnorm', 550),
]
test_benchmarks = [
    ('spectralnorm', 550),
    ('fibm', 40, 1000000),
    ('nbody', 200000),
    ('spectralnorm', 550),
    ('binary', 10),
    #('fibiter', 30),
    ('fibiter2', 30),
    ('fibm', 40, 100000),
]


executables = dict(
    nfs = ('../nefarious/nfs-74f3e92 --noinline', '.nfs'),
    nfs_jit = ('../nefarious/nfsj-74f3e92 --noinline', '.nfs'),
    nfs_inline = ('../nefarious/nfs-74f3e92', '.nfs'),
    nfs_jit_inline = ('../nefarious/nfsj-74f3e92', '.nfs'),
    nfs_inlineinf = ('../nefarious/nfs-a059656', '.nfs'),
    nfs_jit_inlineinf = ('../nefarious/nfsj-a059656', '.nfs'),
    nfs_inline80 = ('../nefarious/nfs-d320827', '.nfs'),
    nfs_jit_inline80 = ('../nefarious/nfsj-d320827', '.nfs'),
    #python = ('python2', '.py'),
    #java = ('java', ''),
    #nfs_parse = ('../nefarious/nfs-74f3e92 --parse', '.nfs'),
)

TEST = 'test' in sys.argv

#_, which, bench, *extra = sys.argv
#please(which, bench, *extra)

for which in ('nfs_jit',): #'nfs_jit_inline80', 'nfs_inline80': #sorted(executables.keys(), key=len, reverse=True):
    print(which, file=sys.stderr)
    for bench, *args in (test_benchmarks if TEST else benchmarks):
        please(which, bench, *[str(x) for x in args])
    print(file=sys.stderr)
    print('='*40, file=sys.stderr)

