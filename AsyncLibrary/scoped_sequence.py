import threading
import collections.abc


class ScopedSequence(collections.abc.MutableSequence):
    def __init__(self, sequence: collections.abc.MutableSequence):
        self.scopeid = threading.local()
        self.scopes = {None: sequence}
        self.lock = threading.Lock()
        self.next = 0

    def fork(self):
        base = getattr(self.scopeid, 'value', None)

        with self.lock:
            id = self.next
            self.scopes[id] = self.scopes[base].copy()
            self.next += 1
            return id

    def kill(self, id=-1):
        if id is None:
            raise RuntimeError(f'default scope cannot be killed')
        if id < 0:
            id = self.scopeid.value
        with self.lock:
            self.scopes.pop(id)

        try:
            if self.scopeid.value == id:
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

    def __getitem__(self, index):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__getitem__(index)

    def __setitem__(self, index, value):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__setitem__(index, value)

    def __delitem__(self, index):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__delitem__(index)

    def __iter__(self):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__iter__()

    def __contains__(self, value):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__contains__(value)

    def __reversed__(self):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__reversed__()

    def __len__(self):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__len__()

    def reverse(self):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].reverse()

    def insert(self, index, value):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].insert(index, value)

    def remove(self, value):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].remove(value)

    def append(self, value):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].append(value)

    def extend(self, values):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].extend(values)

    def __iadd__(self, values):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].__iadd__(values)

    def pop(self, index=-1):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].pop(index)

    def clear(self):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].clear()

    def index(self, value, start=0, stop=None):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].index(value, start, stop)

    def count(self, value):
        id = getattr(self.scopeid, 'value', None)
        return self.scopes[id].count(value)
