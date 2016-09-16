import os
import sys
from subprocess import Popen, PIPE

from . import ParserTests

class CompiledTests(ParserTests):
    """Check the compiled binary behaves correctly"""

    BINARY = './nfs'

    @classmethod
    def setUpClass(cls):
        assert os.path.exists(cls.BINARY), "Can't find `nfs` executable"
    
    def _execute(self, source):
        p = Popen([self.BINARY, "-"], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        p.stdin.write(source + "\n")
        p.stdin.close()
        output = p.stdout.read()
        assert output[-1] == "\n"
        output = output[:-1]
        sys.stderr.write(p.stderr.read())
        return output

del ParserTests

