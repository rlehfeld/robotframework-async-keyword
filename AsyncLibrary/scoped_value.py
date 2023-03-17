import threading


undefined = []


class ScopedValue:
    def __init__(
            self,
            original=undefined,
            *,
            forkvalue=undefined,
    ):    # pylint: disable=dangerous-default-value
        self._scopeid = threading.local()
        if original is undefined:
            self._scopes = {}
        else:
            self._scopes = {None: original}
            try:
                self.__name__ = original.__name__
            except AttributeError:
                pass
            try:
                self.__doc__ = original.__doc__
            except AttributeError:
                pass
        if forkvalue is not undefined:
            self._forkvalue = forkvalue
        self._lock = threading.Lock()
        self._next = 0

    @property
    def scope(self):
        return getattr(self._scopeid, 'value', None)

    def fork(self):
        with self._lock:
            identifier = self._next
            try:
                value = getattr(self, '_forkvalue')
            except AttributeError:
                try:
                    copy = getattr(self._scopes[self.scope], 'copy')
                except AttributeError:
                    value = self._scopes[self.scope]
                else:
                    value = copy()
            self._scopes[identifier] = value
            self._next += 1
            return identifier

    def kill(self, identifier=-1):
        if identifier is None:
            raise RuntimeError('default scope cannot be killed')
        if identifier < 0:
            identifier = self.scope
        with self._lock:
            self._scopes.pop(identifier)

        try:
            if self.scope == identifier:
                del self._scopeid.value
        except AttributeError:
            pass

    def activate(self, identifier):
        with self._lock:
            if identifier is None:
                try:
                    del self._scopeid.value
                except AttributeError:
                    pass
            elif identifier in self._scopes:
                self._scopeid.value = identifier
            else:
                raise RuntimeError(f'a fork with {identifier=} does not exist')

    def get(self):
        with self._lock:
            return self._scopes[self.scope]

    def set(self, value):
        with self._lock:
            self._scopes[self.scope] = value


class ScopedDescriptor:
    def __init__(self, attribute):
        self._attribute = attribute

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return self.instance(instance).get()

    def __set__(self, instance, value):
        return self.instance(instance).set(value)

    def instance(self, instance):
        try:
            return getattr(instance, self._attribute)
        except AttributeError:
            scope = ScopedValue()
            setattr(instance, self._attribute, scope)
            return scope


def scope_parameter(
        obj,
        parameter,
        *,
        forkvalue=undefined,
):    # pylint: disable=dangerous-default-value
    try:
        scope = getattr(obj, f'_scoped_{parameter}')
    except AttributeError:
        scope = None

    if not isinstance(scope, ScopedValue):
        original = getattr(obj, parameter)

        kwargs = {'original': original}
        if forkvalue is not undefined:
            kwargs['forkvalue'] = forkvalue
        scope = ScopedValue(**kwargs)
        setattr(obj, f'_scoped_{parameter}', scope)
        delattr(obj, parameter)

        class PatchedClass(obj.__class__):    # noqa, E501 pylint: disable=too-few-public-methods
            '''
            dummy class which is required
            to replace the existing class
            with a wrapper which includes
            scoped descriptors for save
            multi threaded access
            '''

        setattr(PatchedClass, parameter,
                ScopedDescriptor(f'_scoped_{parameter}'))
        PatchedClass.__name__ = obj.__class__.__name__
        PatchedClass.__doc__ = obj.__class__.__doc__
        obj.__class__ = PatchedClass

    return scope
