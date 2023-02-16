import threading
from concurrent.futures import ThreadPoolExecutor, wait
from functools import wraps
from robot.api.logger import librarylogger
from robot.libraries.BuiltIn import BuiltIn
from robot.libraries.DateTime import convert_time
from robot.running import Keyword


def only_run_on_robot_thread(func):
    @wraps(func)
    def inner(*args, **kwargs):
        thread = threading.currentThread().getName()
        if thread not in librarylogger.LOGGING_THREADS:
            return

        return func(*args, **kwargs)

    return inner


def must_be_run_in_robot_thread(func):
    @wraps(func)
    def inner(*args, **kwargs):
        thread = threading.currentThread().getName()
        if thread not in librarylogger.LOGGING_THREADS:
            raise RuntimeError(
                'Must be used only from robot framework threads.'
            )

        return func(*args, **kwargs)

    return inner


class AsyncLibrary:
    ROBOT_LIBRARY_SCOPE = 'SUITE'
    ROBOT_LISTENER_API_VERSION = 2

    def __init__(self):
        self.ROBOT_LIBRARY_LISTENER = [self]
        self._future = {}
        self._last_thread_handle = 0
        self._executor = ThreadPoolExecutor()
        self._lock = threading.Lock()

        context = BuiltIn()._get_context()
        context.user_keyword = must_be_run_in_robot_thread(
            context.user_keyword
        )

        output = getattr(context, 'output', None)
        xmllogger = getattr(output, '_xmllogger', None)
        writer = getattr(xmllogger, '_writer', None)
        if writer:
            writer.start = only_run_on_robot_thread(writer.start)
            writer.end = only_run_on_robot_thread(writer.end)
            writer.element = only_run_on_robot_thread(writer.element)

    def async_run(self, keyword, *args):
        '''
        Executes the provided Robot Framework keyword in a separate thread
        and immediately returns a handle to be used with async_get
        '''
        context = BuiltIn()._get_context()
        runner = context.get_runner(keyword)
        future = self._executor.submit(
            runner.run, Keyword(keyword, args=args), context
        )

        with self._lock:
            handle = self._last_thread_handle
            self._last_thread_handle += 1
            self._future[handle] = future

        return handle

    def async_get(self, handle, timeout=None):
        '''
        Blocks until the future created by async_run includes a result
        '''
        if timeout:
            timeout = convert_time(timeout, result_format='number')
        try:
            future = self._future.pop(handle)
        except KeyError:
            raise ValueError(f'entry with handle {handle} does not exist')
        return future.result(timeout)

    def async_get_all(self, timeout=None):
        '''
        Blocks until all futures created by async_run include a result
        '''
        if timeout:
            timeout = convert_time(timeout, result_format='number')

        with self._lock:
            future = self._future
            self._future = {}

        futures = list(future.values())

        result = wait(futures, timeout)

        if result.not_done:
            self._future.update({k: v for k, v in futures.items()
                                 if v in result.not_done})
            raise TimeoutError(
                f'{len(result.not_done)} (of {len(futures)}) '
                'futures unfinished'
            )

        for f in result.done:
            f.result()

    def _end_suite(self, suite, attrs):
        self._wait_all()

    def _close(self):
        self._wait_all()

    def _wait_all(self):
        with self._lock:
            futures = list(f for f in self._future.values() if not f.cancel())
            self._future = {}

        wait(futures)
