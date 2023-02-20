import threading


class ScopedValue:
    def __init__(self, default):
        self.scopeid = threading.local()
        self.scopes = {None: default}
        self.lock = threading.Lock()
        self.next = 0

    @property
    def scope(self):
        return getattr(self.scopeid, 'value', None)

    def fork(self):
        with self.lock:
            id = self.next
            try:
                copy = getattr(self.scopes[self.scope], 'copy')
            except AttributeError:
                value = self.scopes[self.scope]
                if isinstance(value, bool):
                    value = False
                elif isinstance(value, int):
                    value = 0
            else:
                value = copy()
            self.scopes[id] = value
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

    def set(self, value):
        self.scopes[self.scope] = value


class ScopedDescriptor:
    def __init__(self, attribute):
        self._attribute = attribute

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return getattr(instance, self._attribute).get()

    def __set__(self, instance, value):
        return getattr(instance, self._attribute).set(value)
