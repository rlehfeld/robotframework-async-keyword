from collections import OrderedDict
from functools import wraps
from threading import RLock


def protect_callable(func):
    @wraps(func)
    def inner(self, *args, **kwargs):
        with self._lock:
            result = func(self, *args, **kwargs)
            if isinstance(result, tuple):
                result = list(result)
            return result
    return inner


class ProtectedOrderedDict(OrderedDict):
    def __init__(self, other=(), /, **kwds):
        self._lock = RLock()
        return super().__init__(other, **kwds)
    __init__.__doc__ = OrderedDict.__init__.__doc__


for name, func in vars(OrderedDict).items():
    if name != '__init__' and callable(func):
        setattr(ProtectedOrderedDict, name, protect_callable(func))
