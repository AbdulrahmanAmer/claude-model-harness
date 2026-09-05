import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calc import add

def test_add():
    assert add(2, 3) == 5
