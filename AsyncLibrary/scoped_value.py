'''
Wrapper around object to make values of parameters actually
thread specific
'''
import threading


_UNDEFINED = object()


class ScopedValue:
    '''
    scope content holder for the different execution
    path that will exists in robot framework, once
    we execute a keyword in a different thread
    '''

    def __init__(
            self,
            original=_UNDEFINED,
            *,
            forkvalue=_UNDEFINED,
    ):
        self._scopeid = threading.local()
        if original is _UNDEFINED:
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
        if forkvalue is not _UNDEFINED:
            self._forkvalue = forkvalue
        self._lock = threading.Lock()
        self._next = 0

    @property
    def scope(self):
        '''
        return the current active scope for a thread
        '''
        return getattr(self._scopeid, 'value', None)

    def fork(self):
        '''
        create a new scope which can be activated in a thread
        through the use of the activate method
        '''
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
        '''
        destroy a scope of. This method does not check, if the
        scope is currently in use by a thread
        '''
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
        '''
        activates a scope for a thread
        '''
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
        '''
        return the current active scope object
        '''
        with self._lock:
            return self._scopes[self.scope]

    def set(self, value):
        '''
        set the current active scope object
        '''
        with self._lock:
            self._scopes[self.scope] = value


class ScopedDescriptor:
    '''
    Descriptor access class
    in order to implement transparently,
    without explicitly changing the robot framework code,
    that in different threads the value of a parameter of an object
    needs to have actually thread specifis values
    '''
    def __init__(self, attribute):
        self._attribute = attribute

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return self.instance(instance).get()

    def __set__(self, instance, value):
        return self.instance(instance).set(value)

    def instance(self, instance):
        '''
        return the scoped instance of an object
        '''
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
        forkvalue=_UNDEFINED,
):
    '''
    decorator an paramter in an object through monkey patching
    so it can have different values in different threads
    as the code in Robot Framework is not prepared for having
    different execution paths
    '''
    try:
        scope = getattr(obj, f'_scoped_{parameter}')
    except AttributeError:
        scope = None

    if not isinstance(scope, ScopedValue):
        original = getattr(obj, parameter)

        kwargs = {'original': original}
        if forkvalue is not _UNDEFINED:
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
