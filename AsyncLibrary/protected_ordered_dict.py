'''
this module provides a very generic wrapper around ordered dictionaries
which will become thread save through using locks and returning lists
instead of views
'''
from collections import OrderedDict
from collections.abc import MappingView
from functools import wraps
from threading import RLock


def protect_callable(func):
    '''
    simple decorator for callables
    only execute the original method
    once the lock inside the class is
    fetched. Further, in case the result
    is a MappingView, transform the result
    into a regular list
    '''
    @wraps(func)
    def inner(self, *args, **kwargs):
        with self._lock:    # pylint: disable=protected-access
            result = func(self, *args, **kwargs)
            if isinstance(result, (MappingView, tuple)):
                result = list(result)
            return result
    return inner


class ProtectedOrderedDict(OrderedDict):
    '''
    very simple class wrapper around OrderedDict
    which is thread save when using and extending
    across different threads
    '''
    def __init__(self, other=(), /, **kwds):
        self._lock = RLock()
        super().__init__(other, **kwds)
    __init__.__doc__ = OrderedDict.__init__.__doc__


for name, value in vars(OrderedDict).items():
    if name != '__init__' and callable(value):
        setattr(ProtectedOrderedDict, name, protect_callable(value))
