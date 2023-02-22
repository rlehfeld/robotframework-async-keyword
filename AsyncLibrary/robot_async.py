import signal
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, wait
from functools import wraps
from .scoped_value import ScopedValue, ScopedDescriptor
from robot.api import logger
from robot.api.logger import librarylogger
from robot.libraries.BuiltIn import BuiltIn
from robot.libraries.DateTime import convert_time
from robot.running import Keyword


def only_run_on_robot_thread(func):
    @wraps(func)
    def inner(*args, **kwargs):
        thread = threading.currentThread().name
        if thread not in librarylogger.LOGGING_THREADS:
            return

        return func(*args, **kwargs)

    return inner


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
        if exc_type:
            tb = traceback.TracebackException(
                exc_type, exc_val, exc_tb
            )
            for s in tb.format():
                logger.console(s)


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

        context = BuiltIn()._get_context()
        output = getattr(context, 'output', None)
        xmllogger = getattr(output, '_xmllogger', None)
        writer = getattr(xmllogger, '_writer', None)
        if writer:
            writer.start = only_run_on_robot_thread(writer.start)
            writer.end = only_run_on_robot_thread(writer.end)
            writer.element = only_run_on_robot_thread(writer.element)

    def _run(self, scope, fn, *args, **kwargs):
        with scope:
            return fn(*args, **kwargs)

    def async_run(self, keyword, *args):
        '''
        Executes the provided Robot Framework keyword in a separate thread
        and immediately returns a handle to be used with _*Async Get*_
        '''
        context = BuiltIn()._get_context()
        runner = context.get_runner(keyword)
        scope = ScopedContext()
        with BlockSignals():
            future = self._executor.submit(
                self._run, scope,
                runner.run, Keyword(keyword, args=args), context
            )
        future._scope = scope

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
