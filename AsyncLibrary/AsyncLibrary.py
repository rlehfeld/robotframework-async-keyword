# '''
# Actual implementation of the Robot Framework extension
# It uses quite extensivle monkey patching as Robot Framework is not
# prepared for multi threaded execution of keywords
#
# Just saying this, it is not guaranteed that it will work under all
# circumstances or for older or newer version that we are using it for
# '''
import threading
import traceback
import builtins
from concurrent.futures import ThreadPoolExecutor, wait
from functools import wraps
from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn, RobotNotRunningError
from robot.libraries.DateTime import convert_time
try:
    from robot.running.userkeywordrunner import KeywordData
    _RUN_REQUIRES_KEYWORDRESULT = True
except ImportError:
    from robot.running import Keyword as KeywordData
    _RUN_REQUIRES_KEYWORDRESULT = False
try:
    from robot.running.model import Argument
except ImportError:
    def Argument(*args):  # pylint: disable=invalid-name
        """legacy argument function before RF 7.0.1"""
        return tuple(args)
from robot.result import Keyword as KeywordResult
from robot.output.logger import LOGGER

from robot_async import Postpone, ScopedContext
from scoped_value import scope_parameter, _UNDEFINED
from protected_ordered_dict import ProtectedOrderedDict


class AsyncLibrary:
    '''
    actual implementation class for the AsyncLibrary
    Robot Framework extension
    '''
    ROBOT_LIBRARY_SCOPE = 'SUITE'
    ROBOT_LISTENER_API_VERSION = 2

    def __init__(self):
        self.ROBOT_LIBRARY_LISTENER = [self]    # pylint: disable=invalid-name
        self._futures = {}
        self._last_thread_handle = 0
        self._executor = ThreadPoolExecutor()
        self._lock = threading.Lock()
        self._postpone = None
        if self._is_robot_running():
            self._init_postpone()

    @staticmethod
    def _is_robot_running():
        try:
            BuiltIn()._get_context()    # noqa, E501  pylint: disable=protected-access
            return True
        except RobotNotRunningError:
            return False

    def _init_postpone(self):
        if self._postpone is None:
            self._postpone = Postpone()

    def _run(self, scope, postpone_id, func, *args, **kwargs):
        with self._postpone(postpone_id), scope:
            if _RUN_REQUIRES_KEYWORDRESULT:
                kwargs['result'] = KeywordResult()
            return func(*args, **kwargs)

    def async_run(self, keyword, *args, **kwargs):
        '''
        Executes the provided Robot Framework keyword in a separate thread
        and immediately returns a handle to be used with _*Async Get*_
        '''
        context = BuiltIn()._get_context()    # noqa, E501  pylint: disable=protected-access
        runner = context.get_runner(keyword)
        scope = ScopedContext()
        postpone_id = self._postpone.fork()

        future = self._executor.submit(
            self._run, scope, postpone_id,
            runner.run,
            KeywordData(
                keyword,
                args=tuple(args) + tuple(
                    Argument(key, value) for key, value in kwargs.items()
                )
            ),
            context=context
        )
        future._scope = scope    # pylint: disable=protected-access
        future._postpone_id = postpone_id    # pylint: disable=protected-access
        with self._lock:
            handle = self._last_thread_handle
            self._last_thread_handle += 1
            self._futures[handle] = future

        return handle

    def _parse_handle(self, handle):
        futures = {}
        retlist = True
        with self._lock:
            if handle is None:
                handles = list(self._futures.keys())
                handles.sort()
            else:
                try:
                    handles = list(handle)
                except TypeError:
                    handles = [handle]
                    retlist = False
            for item in handles:
                if item in futures:
                    raise RuntimeError(f'handle={item} passed more than once')
                futures[item] = self._futures[item]
            for item in handles:
                # in two steps so that no future get lost
                # in case of an error
                self._futures.pop(item)

            return retlist, handles, futures

    def async_get(self, handle=None, timeout=None):
        '''
        Blocks until the keyword(s) spawned by _*Async Run*_ include a result.
        '''
        if timeout:
            timeout = convert_time(timeout, result_format='number')

        retlist, handles, futures = self._parse_handle(handle)

        result = wait(futures.values(), timeout)

        exceptions = [e for e in (
            futures[h].exception() for h in handles
            if futures[h] in result.done
        ) if e]

        if result.not_done:
            with self._lock:
                self._futures.update({k: v for k, v in futures.items()
                                     if v in result.not_done})
            exceptions.append(
                TimeoutError(
                    f'{len(result.not_done)} (of {len(futures)}) '
                    'futures unfinished'
                )
            )

        for item in handles:
            future = futures[item]
            if future in result.done:
                self._postpone.replay(
                    future._postpone_id    # pylint: disable=protected-access
                )

        if exceptions:
            if len(exceptions) > 1:
                eg = getattr(builtins, 'ExceptionGroup', None)
                if eg is not None:
                    raise eg(
                        'async_get caught exceptions',
                        exceptions
                    )
            raise exceptions[-1]

        ret = [futures[h].result() for h in handles]

        if retlist:
            return ret
        return ret[-1]

    def _start_suite(
            self,
            suite,    # pylint: disable=unused-argument
            attrs,    # pylint: disable=unused-argument
    ):
        '''
        Start Suite callback.
        '''
        self._init_postpone()

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
            for handle, future in self._futures.items():
                if future.cancel():
                    future._scope.kill()    # pylint: disable=protected-access
                else:
                    handles.append(handle)
                    futures[handle] = future
            self._futures.clear()

        wait(futures.values())

        handles.sort()
        for handle in handles:
            future = futures[handle]
            self._postpone.replay(
                future._postpone_id    # pylint: disable=protected-access
            )
