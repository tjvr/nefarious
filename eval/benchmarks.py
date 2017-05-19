from datetime import datetime
import logging
import os
from queue import *
from shlex import quote
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlencode


REPO_PATH = '/home/tim/nefarious/'
HOST = 'cray'
REMOTE_PATH = 'nefarious'
EXE_PATH = '/home/tim/codespeed/tools/nfsexe/'

EXES = [
    'nfsj',
    'nfs',
]

OPTIONS = [
    'nfsj',
    'nfs',
    'nfsj --noinline',
    'nfs --noinline',
]

OPTIONS_CAN_SLOW = [
    'nfsj',
]

BENCHMARKS = [
    'fib-m',
    'nbody',
    'fib-f',
    #'binary',
    'spectral-norm',
    'binary16',
    'nbody10',
    'nqueens',
]

SLOW_BENCHMARKS = [
    'nbody10',
]

PRIORITY = [
    (options, name)
    for options in OPTIONS
    for name in BENCHMARKS
    if not (name in SLOW_BENCHMARKS and options not in OPTIONS_CAN_SLOW)
]


def ssh_popen(args, cwd=None, **kwargs):
    cmd = ' '.join(map(quote, args))
    log.info(f'SSH: {HOST}:{cwd}$ {cmd}')
    if cwd:
        cmd = f'cd {cwd}; {cmd}'
    return subprocess.Popen(['ssh', HOST, cmd], **kwargs)

def ssh_call(*popenargs, timeout=None, **kwargs):
    with ssh_popen(*popenargs, **kwargs) as p:
        try:
            return p.wait(timeout=timeout)
        except:
            p.kill()
            p.wait()
            raise

def ssh_check_call(*popenargs, **kwargs):
    retcode = ssh_call(*popenargs, **kwargs)
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd)
    return 0


compile_queue = Queue() # (which, sha)
benchmark_queue = PriorityQueue() # (which, sha, benchmark)

seen_shas = set()

def submit(sha):
    assert len(sha) > 7
    if sha in seen_shas:
        log.warn(f'already seen sha: {sha[:7]}')
        return
    seen_shas.add(sha)

    # TODO
    # subprocess.check_call(
    #     ['git', 'push', '-f', f'{HOST}:{REMOTE_PATH}', f'{sha}:master'],
    #     cwd=REPO_PATH
    # )
    for which in EXES:
        check_compile(which, sha)

def check_compile(which, sha):
    path = os.path.join(EXE_PATH, f'{which}-{sha[:7]}')
    if os.path.exists(path):
        print(f'found: {path}')
        queue_benchmarks(which, sha)
    else:
        print(f'missing: {path}')
        compile_queue.put((which, sha))

def compile(which, sha):
    ssh_check_call(['git', 'checkout', '-f', sha], cwd=REMOTE_PATH)
    ssh_check_call(['make', 'clean'], cwd=REMOTE_PATH, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return ssh_popen(['make', which], cwd=REMOTE_PATH, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def compile_finished(which, sha, retcode):
    # TODO `make` should output to which-sha
    subprocess.check_call(['scp', f'{HOST}:{REMOTE_PATH}/{which}', f'{which}-{sha[:7]}'], cwd=EXE_PATH)
    queue_benchmarks(which, sha)

def compile_error(which, sha, retcode, p):
    if retcode != 0:
        log.error(f'compile {which} {sha} exited with code {retcode}')
        log.error('=' * 60)
        log.error('\n'.join(p.stderr.read().decode('utf-8').split('\n')[-60:]))
        return

def queue_benchmarks(which, sha):
    options = [o for o in OPTIONS if o.split(' ')[0] == which]
    for name in BENCHMARKS:
        for opt in options:
            if name in SLOW_BENCHMARKS and opt not in OPTIONS_CAN_SLOW:
                continue
            priority = PRIORITY.index((opt, name))
            benchmark_queue.put((priority, (sha, opt, name)))

#------------------------------------------------------------------------------

def compile_thread():
    workers = []
    while True:
        if len(workers) < 4 and not compile_queue.empty():
            which, sha = compile_queue.get()
            p = compile(which, sha)
            time.sleep(2) # workaround strange try_compile_cache sync problem
            workers.append((which, sha, p))

        for which, sha, p in workers:
            retcode = p.poll()
            if retcode is None:
                continue
            if retcode == 0:
                compile_finished(which, sha, retcode)
            else:
                compile_error(which, sha, retcode, p)
            workers.remove((which, sha, p))
            if compile_queue.empty() and len(workers) == 0:
                log.info('compile queue FINISHED!')
            break

        time.sleep(0.1)

def benchmark_thread():
    while True:
        if benchmark_queue.empty():
            log.info('benchmark queue EMPTY!')
        _, (sha, options, name) = benchmark_queue.get(block=True)
        which, *args = options.split(' ')
        try:
            data = benchmark(which, sha, args, name)
            add(data)
        except RPythonError as e:
            log.error(e.msg)

#------------------------------------------------------------------------------

SYS = 'Linux'
ENV = 'clive'

# You need to enter the real URL and have the server running
CODESPEED_URL = 'http://codespeed.clive.tjvr.org/'

def add(data):
    params = urlencode(data)
    response = 'None'
    logging.info('Saving {benchmark} for {executable} at {commitid}'.format(**data))
    try:
        f = urllib.request.urlopen(CODESPEED_URL + 'result/add/', params.encode('utf-8'))
    except urllib.HTTPError as e:
        logging.error(str(e))
        logging.error(e.read())
        return
    response = f.read().decode('utf-8')
    f.close()
    logging.info(f'RESPONSE: {response}')
    logging.info('---')

class RPythonError(Exception):
    def __init__(self, msg):
        assert isinstance(msg, str)
        self.msg = msg

def time_cmd(args, cwd=EXE_PATH):
    p = subprocess.Popen(['/usr/bin/time', '-f%U'] + args, cwd=cwd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    timing = p.stderr.read().strip()
    #assert p.returncode == 0, p.returncode
    try:
        user = float(timing)
    except ValueError:
        raise RPythonError(timing.decode('utf-8'))
    cmd = ' '.join(args)
    log.info(f'time {cmd} --> {user}s')
    return user

def mean(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)

def benchmark(which, sha, args, benchmark, branch='default', samples=8):
    executable = '{}-{}'.format(which, sha[:7])
    exe_path = os.path.join(EXE_PATH, executable)
    file_path = os.path.join(EXE_PATH, benchmark)
    assert os.path.exists(file_path)

    parse_time = mean([
        time_cmd([os.path.join('./', executable), '--parse', benchmark])
        for i in range(3)
    ])

    results = [
        time_cmd([os.path.join('./', executable)] + args + [benchmark])
        for i in range(samples)
    ]

    # TODO subtract parse_time!

    user = mean(results)

    cmd = ' '.join([executable] + args)
    log.info(f'time {cmd} --> parsed in {parse_time}s')
    log.info(f'time {cmd} --> mean {user}s')

    if args:
        which = which.replace('s', 'z')
    cmd = ' '.join([which] + args)
    return dict(
        commitid = sha,
        branch = branch,
        project = 'Nefarious',
        executable = '{} on {}'.format(cmd, SYS),
        benchmark = benchmark,
        environment = ENV,
        #revision_date = ???

        result_value = user,
        max = max(results),
        min = min(results),
        #std_dev
    )

#------------------------------------------------------------------------------

handler = logging.StreamHandler()
formatter = logging.Formatter('{asctime} [{threadName} {levelname}] {message}', style='{')
       # %(asctime)s [%(threadName)-s] [%(levelname)-s] %(message)s")
handler.setFormatter(formatter)

log = logging.getLogger()
log.addHandler(handler)
log.setLevel(logging.INFO)

threading.Thread(target=compile_thread, name='Compile').start()
threading.Thread(target=benchmark_thread, name='Benchmark').start()

# TODO exit cleanly

#from pprint import pprint
#pprint(PRIORITY)

while True:
    try:
        sha = input('sha? ')
    except KeyboardInterrupt:
        continue
    if len(sha) == 40:
        submit(sha)
    else:
        print('bad sha')

