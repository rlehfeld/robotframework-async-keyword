import signal
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, wait
from functools import wraps
from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn
from robot.libraries.DateTime import convert_time
from robot.running import Keyword
from robot.output.logger import LOGGER
from .scoped_value import scope_parameter, undefined
from .protected_ordered_dict import ProtectedOrderedDict


class Postpone:
    def __init__(self):
        self._lock = threading.Lock()
        self._postponed = {}
        self._id = threading.local()
        self._next = 0

        self._context = BuiltIn()._get_context()
        output = getattr(self._context, 'output', None)
        xmllogger = getattr(output, '_xmllogger', None)
        writer = getattr(xmllogger, '_writer', None)
        if writer:
            writer.start = self.postpone(writer.start)
            writer.end = self.postpone(writer.end)
            writer.element = self.postpone(writer.element)

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

    def postpone(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            postpone_id = self.get()
            if postpone_id is None:
                return func(*args, **kwargs)

            with self._lock:
                self._postponed[postpone_id].append([
                    func, list(args), dict(kwargs)
                ])
                return None

        inner._original = func    # pylint: disable=protected-access
        return inner

    def replay(self, postpone_id):
        while True:
            with self._lock:
                try:
                    func = self._postponed[postpone_id].pop(0)
                except IndexError:
                    del self._postponed[postpone_id]
                    break

            func[0](*func[1], **func[2])

    def close(self):
        output = getattr(self._context, 'output', None)
        xmllogger = getattr(output, '_xmllogger', None)
        writer = getattr(xmllogger, '_writer', None)
        if writer:
            writer.start = writer.start._original    # noqa, E501 pylint: disable=protected-access
            writer.end = writer.end._original    # noqa, E501  pylint: disable=protected-access
            writer.element = writer.element._original    # noqa, E501  pylint: disable=protected-access

    def __call__(self, postpone_id):
        self.activate(postpone_id)
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.deactivate()


class BlockSignals:
    def __init__(self):
        self._current = []
        try:
            self._sigmask = getattr(signal, 'pthread_sigmask')
        except AttributeError:
            self._sigmask = None

    def __enter__(self):
        if self._sigmask:
            self._current.append(
                self._sigmask(
                    signal.SIG_BLOCK,
                    [
                        signal.SIGTERM,
                        signal.SIGINT,
                    ]
                )
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._sigmask:
            self._sigmask(signal.SIG_SETMASK, self._current.pop())


logger_scope = scope_parameter(
    LOGGER,
    '_started_keywords',
    forkvalue=0,
)

if LOGGER._console_logger:    # pylint: disable=protected-access
    try:
        CONSOLE_LOGGER_SCOPE = scope_parameter(
            LOGGER._console_logger.logger,    # noqa, E501  pylint: disable=protected-access
            '_started_keywords',
            forkvalue=0,
        )
    except AttributeError:
        CONSOLE_LOGGER_SCOPE = None


class ScopedContext:
    _attributes = [
        ['test'],
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
        'test': None,
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
            forkvalue = self._construct.get(p, undefined)
            scope = scope_parameter(parent, p, forkvalue=forkvalue)
            if not isinstance(self._context.namespace._kw_store.libraries,
                              ProtectedOrderedDict):
                self._context.namespace._kw_store.libraries = (
                    ProtectedOrderedDict(
                        self._context.namespace._kw_store.libraries
                    )
                )
            self._forks.append(scope.fork())

        self._logger = logger_scope.fork()
        if CONSOLE_LOGGER_SCOPE:
            self._console_logger = CONSOLE_LOGGER_SCOPE.fork()

    def activate(self):
        forks = self._forks

        for a, c in zip(self._attributes, forks):
            current = self._context
            for p in a[0:-1]:
                current = getattr(current, p)
            scope = getattr(current, f'_scoped_{a[-1]}')
            scope.activate(c)

        logger_scope.activate(self._logger)
        if CONSOLE_LOGGER_SCOPE:
            CONSOLE_LOGGER_SCOPE.activate(
                self._console_logger
            )

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

        logger_scope.kill(self._logger)
        if CONSOLE_LOGGER_SCOPE:
            CONSOLE_LOGGER_SCOPE.kill(
                self._console_logger
            )

    def __enter__(self):
        self.activate()
        return self

    @staticmethod
    def _isexceptioninstance(exc, what):
        if not exc:
            return False
        if isinstance(exc, what):
            return True
        context = getattr(exc, '__context__', None)
        if context:
            return ScopedContext._isexceptioninstance(context, what)
        return False

    @staticmethod
    def _trace_exception(exc):
        if not exc:
            return

        if ScopedContext._isexceptioninstance(
                exc, (SyntaxError, RuntimeError, AttributeError)):
            tb = traceback.TracebackException.from_exception(
                    exc
            )
            for s in tb.format():
                logger.console(s)

        get_errors = getattr(exc, 'get_errors', None)
        if get_errors:
            errors = get_errors()
        else:
            errors = getattr(exc, 'exceptions', ())

        for error in errors:
            if error is not exc:
                ScopedContext._trace_exception(error)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._trace_exception(exc_val)

        self.kill()


class AsyncLibrary:
    ROBOT_LIBRARY_SCOPE = 'SUITE'
    ROBOT_LISTENER_API_VERSION = 2

    def __init__(self):
        self.ROBOT_LIBRARY_LISTENER = [self]    # pylint: disable=invalid-name
        self._future = {}
        self._last_thread_handle = 0
        with BlockSignals():
            self._executor = ThreadPoolExecutor()
        self._lock = threading.Lock()
        self._postpone = Postpone()

    def _run(self, scope, postpone_id, fn, *args, **kwargs):
        with self._postpone(postpone_id), scope:
            return fn(*args, **kwargs)

    def async_run(self, keyword, *args):
        '''
        Executes the provided Robot Framework keyword in a separate thread
        and immediately returns a handle to be used with _*Async Get*_
        '''
        context = BuiltIn()._get_context()    # noqa, E501  pylint: disable=protected-access
        runner = context.get_runner(keyword)
        scope = ScopedContext()
        postpone_id = self._postpone.fork()

        with BlockSignals():
            future = self._executor.submit(
                self._run, scope, postpone_id,
                runner.run, Keyword(keyword, args=args), context
            )
        future._scope = scope    # pylint: disable=protected-access
        future._postpone_id = postpone_id    # pylint: disable=protected-access
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
                handles.sort()
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
                self._postpone.replay(
                    f._postpone_id    # pylint: disable=protected-access
                )

        if exceptions:
            if len(exceptions) > 1:
                try:
                    raise ExceptionGroup(
                        'async_get caught exceptions',
                        exceptions)
                except NameError:
                    raise exceptions[-1]    # noqa, E501 pylint: disable=raise-missing-from
            else:
                raise exceptions[-1]

        ret = [future[h].result() for h in handles]

        if retlist:
            return ret
        return ret[-1]

    def async_get_all(self, timeout=None):
        '''
        Blocks until the keyword spawned by _*Async Run*_ include a result.
        '''
        return self.async_get(timeout=timeout)

    def _end_suite(
            self,
            suite,    # pylint: disable=unused-argument
            attrs,    # pylint: disable=unused-argument
    ):
        '''
        End Suite callback. Wait for all asynchronous started keywords to
        terminate
        '''
        self._wait_all()

    def _close(self):
        '''
        Cleanup Method which is called by robot framework when the object is
        about to be removed
        '''
        self._wait_all()
        self._executor.shutdown()
        self._postpone.close()

    def _wait_all(self):
        '''
        wait and cancel not yet triggered asynchronous keyword executions
        and post the output which was generated during the execution
        '''
        futures = {}
        handles = []
        with self._lock:
            for h, f in self._future.items():
                if f.cancel():
                    f._scope.kill()    # pylint: disable=protected-access
                else:
                    handles.append(h)
                    futures[h] = f
            self._future.clear()

        wait(futures.values())

        handles.sort()
        for h in handles:
            f = futures[h]
            self._postpone.replay(
                f._postpone_id    # pylint: disable=protected-access
            )
