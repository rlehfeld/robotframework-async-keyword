import threading
from concurrent.futures import ThreadPoolExecutor
from robot.libraries.BuiltIn import BuiltIn
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
        with self._lock:
            handle = self._last_thread_handle
            self._last_thread_handle += 1
        self._future[handle] = self._executor.submit(
            runner.run, Keyword(keyword, args=args), context
        )
        return handle

    def async_get(self, handle, timeout=None):
        '''
        Blocks until the future created by async_run includes a result
        '''
        try:
            future = self._future.pop(handle)
        except KeyError:
            raise ValueError('entry with handle {handle} does not exist')
        return future.result(timeout)
