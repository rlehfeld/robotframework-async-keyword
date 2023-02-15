import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from robot.libraries.BuiltIn import BuiltIn
from robot.libraries.DateTime import convert_time
from robot.running import Keyword
from robot.running.userkeyword import UserKeywordRunner


class AsyncLibrary:
    def __init__(self):
        self._future = {}
        self._last_thread_handle = 0
        self._executor = ThreadPoolExecutor()
        self._lock = threading.Lock()

    def async_run(self, keyword, *args):
        '''
        Executes the provided Robot Framework keyword in a separate thread
        and immediately returns a handle to be used with async_get
        '''
        context = BuiltIn()._get_context()
        runner = context.get_runner(keyword)
        if isinstance(runner, UserKeywordRunner):
            raise ValueError(
                'async_run cannot be used for user defined '
                'keywords as the output xml file will get corrupted'
            )

        future = self._executor.submit(
            runner.run, Keyword(keyword, args=args), context
        )

        with self._lock:
            handle = self._last_thread_handle
            self._last_thread_handle += 1
            self._future[handle] = future

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
            futures = list(self._future.values())
            self._future = {}

        for f in list(as_completed(futures, timeout)):
            f.results()
