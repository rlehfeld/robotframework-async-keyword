from collections import OrderedDict
from collections.abc import MappingView
from functools import wraps
from threading import RLock


def protect_callable(func):
    @wraps(func)
    def inner(self, *args, **kwargs):
        with self._lock:    # pylint: disable=protected-access
            result = func(self, *args, **kwargs)
            if isinstance(result, (MappingView, tuple)):
                result = list(result)
            return result
    return inner


class ProtectedOrderedDict(OrderedDict):
    def __init__(self, other=(), /, **kwds):
        self._lock = RLock()
        super().__init__(other, **kwds)
    __init__.__doc__ = OrderedDict.__init__.__doc__


for name, value in vars(OrderedDict).items():
    if name != '__init__' and callable(value):
        setattr(ProtectedOrderedDict, name, protect_callable(value))
