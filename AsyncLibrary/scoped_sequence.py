import threading
import collections.abc


class ScopedSequence(collections.abc.MutableSequence):
    def __init__(self, sequence: collections.abc.MutableSequence):
        self.scopeid = threading.local()
        self.scopes = {None: sequence}
        self.lock = threading.Lock()
        self.next = 0

    @property
    def scope(self):
        return getattr(self.scopeid, 'value', None)

    def fork(self):
        with self.lock:
            id = self.next
            self.scopes[id] = self.scopes[self.scope].copy()
            self.next += 1
            return id

    def kill(self, id=-1):
        if id is None:
            raise RuntimeError('default scope cannot be killed')
        if id < 0:
            id = self.scope
        with self.lock:
            self.scopes.pop(id)

        try:
            if self.scope == id:
                del self.scopeid.value
        except AttributeError:
            pass

    def activate(self, id):
        with self.lock:
            if id is None:
                try:
                    del self.scopeid.value
                except AttributeError:
                    pass
            elif id in self.scopes:
                self.scopeid.value = id
            else:
                raise RuntimeError(f'a fork with {id=} does not exist')

    def get(self):
        return self.scopes[self.scope]

    def __getitem__(self, index):
        return self.scopes[self.scope].__getitem__(index)

    def __setitem__(self, index, value):
        return self.scopes[self.scope].__setitem__(index, value)

    def __delitem__(self, index):
        return self.scopes[self.scope].__delitem__(index)

    def __iter__(self):
        return self.scopes[self.scope].__iter__()

    def __contains__(self, value):
        return self.scopes[self.scope].__contains__(value)

    def __reversed__(self):
        return self.scopes[self.scope].__reversed__()

    def __len__(self):
        return self.scopes[self.scope].__len__()

    def reverse(self):
        return self.scopes[self.scope].reverse()

    def insert(self, index, value):
        return self.scopes[self.scope].insert(index, value)

    def remove(self, value):
        return self.scopes[self.scope].remove(value)

    def append(self, value):
        return self.scopes[self.scope].append(value)

    def extend(self, values):
        if isinstance(values, ScopedSequence):
            values = values.get()
        return self.scopes[self.scope].extend(values)

    def __add__(self, values):
        if isinstance(values, ScopedSequence):
            values = values.get()
        return self.scopes[self.scope].__add__(values)

    def __iadd__(self, values):
        if isinstance(values, ScopedSequence):
            values = values.get()
        self.scopes[self.scope] = self.scopes[self.scope].__iadd__(values)
        return self

    def pop(self, index=-1):
        return self.scopes[self.scope].pop(index)

    def clear(self):
        return self.scopes[self.scope].clear()

    def index(self, value, start=0, stop=None):
        return self.scopes[self.scope].index(value, start, stop)

    def count(self, value):
        return self.scopes[self.scope].count(value)
