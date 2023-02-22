import signal
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, wait
from functools import wraps
from .scoped_value import ScopedValue, ScopedDescriptor
from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn
from robot.libraries.DateTime import convert_time
from robot.running import Keyword
from robot.running.statusreporter import StatusReporter


def PatchExit(func):
    @wraps(func)
    def inner(this, exc_type, exc_val, exc_tb):
        if exc_type and exc_type is RuntimeError:
            tb = traceback.TracebackException(
                exc_type, exc_val, exc_tb
            )
            for s in tb.format():
                logger.console(s)

        return func(this, exc_type, exc_val, exc_tb)

    return inner


StatusReporter.__exit__ = PatchExit(StatusReporter.__exit__)


class Postpone:
    def __init__(self):
        self._lock = threading.Lock()
        self._postponed = {}
        self._id = threading.local()
        self._next = 0

        context = BuiltIn()._get_context()
        output = getattr(context, 'output', None)
        xmllogger = getattr(output, '_xmllogger', None)
        writer = getattr(xmllogger, '_writer', None)
        if writer:
            writer.start = self.decorator(writer.start)
            writer.end = self.decorator(writer.end)
            writer.element = self.decorator(writer.element)

    def fork(self):
        with self._lock:
            postpone_id = self._next
            self._next += 1
        return postpone_id

    def activate(self, postpone_id):
        with self._lock:
            self._postponed[postpone_id] = []
        self._id.value = postpone_id

    def deactivate(self):
        del self._id.value

    def get(self):
        try:
            return getattr(self._id, 'value')
        except AttributeError:
            return None

    def decorator(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            postpone_id = self.get()
            if postpone_id is None:
                return func(*args, **kwargs)

            else:
                with self._lock:
                    self._postponed[postpone_id].append([
                        func, list(args), dict(kwargs)
                    ])

        return inner

    def replay(self, postpone_id):
        while True:
            with self._lock:
                try:
                    func = self._postponed[postpone_id].pop(0)
                except IndexError:
                    break
            func[0](*func[1], **func[2])

    def __call__(self, postpone_id):
        self.activate(postpone_id)
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.deactivate()


POSTPONE = Postpone()


class BlockSignals:
    def __init__(self):
        try:
            self._sigmask = getattr(signal, 'pthread_sigmask')
        except AttributeError:
            self._sigmask = None

    def __enter__(self):
        if self._sigmask:
            self._current = self._sigmask(
                signal.SIG_BLOCK,
                [
                    signal.SIGTERM,
                    signal.SIGINT,
                ]
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._sigmask:
            self._sigmask(signal.SIG_SETMASK, self._current)


class ScopedContext:
    _attributes = [
        ['user_keywords'],
        ['step_types'],
        ['timeout_occurred'],
        ['namespace', 'variables', '_scopes'],
        ['namespace', 'variables', '_variables_set', '_scopes'],
        ['_started_keywords'],
        ['in_suite_teardown'],
        ['in_test_teardown'],
        ['in_keyword_teardown'],
    ]

    _construct = {
        '_started_keywords': 0,
        'timeout_occurred': False,
        'in_suite_teardown': False,
        'in_test_teardown': False,
        'in_keyword_teardown': 0,
    }

    def __init__(self):
        self._context = BuiltIn()._get_context()
        self._forks = []
        for a in self._attributes:
            current = self._context
            for p in a:
                parent = current
                current = getattr(parent, p)
            try:
                scope = getattr(parent, f'_scoped_{p}')
            except AttributeError:
                scope = None
            finally:
                if not isinstance(scope, ScopedValue):
                    kwargs = {'default': current}
                    if p in self._construct:
                        kwargs['forkvalue'] = self._construct[p]
                    scope = ScopedValue(**kwargs)
                    setattr(parent, f'_scoped_{p}', scope)
                    delattr(parent, p)

                    class PatchedClass(parent.__class__):
                        pass

                    setattr(PatchedClass, p, ScopedDescriptor(f'_scoped_{p}'))
                    PatchedClass.__name__ = parent.__class__.__name__
                    PatchedClass.__doc__ = parent.__class__.__doc__
                    parent.__class__ = PatchedClass

            self._forks.append(scope.fork())

    def activate(self):
        forks = self._forks

        for a, c in zip(self._attributes, forks):
            current = self._context
            for p in a[0:-1]:
                current = getattr(current, p)
            scope = getattr(current, f'_scoped_{a[-1]}')
            scope.activate(c)

    def kill(self):
        forks = self._forks
        self._forks = []
        for a, c in zip(self._attributes, forks):
            if c is not None:
                current = self._context
                for p in a[0:-1]:
                    current = getattr(current, p)
                scope = getattr(current, f'_scoped_{a[-1]}')
                scope.kill(c)
            self._forks.append(None)

    def __enter__(self):
        self.activate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.kill()


class AsyncLibrary:
    ROBOT_LIBRARY_SCOPE = 'SUITE'
    ROBOT_LISTENER_API_VERSION = 2

    def __init__(self):
        self.ROBOT_LIBRARY_LISTENER = [self]
        self._future = {}
        self._last_thread_handle = 0
        with BlockSignals():
            self._executor = ThreadPoolExecutor()
        self._lock = threading.Lock()

    def _run(self, scope, postpone_id, fn, *args, **kwargs):
        with POSTPONE(postpone_id), scope:
            return fn(*args, **kwargs)

    def async_run(self, keyword, *args):
        '''
        Executes the provided Robot Framework keyword in a separate thread
        and immediately returns a handle to be used with _*Async Get*_
        '''
        context = BuiltIn()._get_context()
        runner = context.get_runner(keyword)
        scope = ScopedContext()
        postpone_id = POSTPONE.fork()

        with BlockSignals():
            future = self._executor.submit(
                self._run, scope, postpone_id,
                runner.run, Keyword(keyword, args=args), context
            )
        future._scope = scope
        future._postpone_id = postpone_id
        with self._lock:
            handle = self._last_thread_handle
            self._last_thread_handle += 1
            self._future[handle] = future

        return handle

    def async_get(self, handle=None, timeout=None):
        '''
        Blocks until the keyword(s) spawned by _*Async Run*_ include a result.
        '''
        if timeout:
            timeout = convert_time(timeout, result_format='number')

        future = {}
        retlist = True
        with self._lock:
            if handle is None:
                handles = list(self._future.keys())
            else:
                try:
                    handles = list(handle)
                except TypeError:
                    handles = [handle]
                    retlist = False
            for h in handles:
                future[h] = self._future[h]
            for h in handles:
                # in two steps so that no future get lost
                # in case of an error
                self._future.pop(h)

        result = wait(future.values(), timeout)

        exceptions = [e for e in (
            future[h].exception() for h in handles
            if future[h] in result.done
        ) if e]

        if result.not_done:
            with self._lock:
                self._future.update({k: v for k, v in future.items()
                                     if v in result.not_done})
            exceptions.append(
                TimeoutError(
                    f'{len(result.not_done)} (of {len(future)}) '
                    'futures unfinished'
                )
            )

        for h in handles:
            f = future[h]
            if f in result.done:
                POSTPONE.replay(f._postpone_id)

        if exceptions:
            raise exceptions[-1]
            # TODO: with Python 3.11 use ExceptionGroup
            #       currently still stuck with Python 3.9

        ret = [future[h].result() for h in handles]

        if retlist:
            return ret
        return ret[-1]

    def async_get_all(self, timeout=None):
        '''
        Blocks until the keyword spawned by _*Async Run*_ include a result.
        '''
        return self.async_get(timeout=timeout)

    def _end_suite(self, suite, attrs):
        self._wait_all()

    def _close(self):
        self._wait_all()
        self._executor.shutdown()

    def _wait_all(self):
        futures = []
        with self._lock:
            for f in self._future.values():
                if f.cancel():
                    f._scope.kill()
                else:
                    futures.append(f)
            self._future.clear()

        wait(futures)

        for f in futures:
            POSTPONE.replay(f._postpone_id)
