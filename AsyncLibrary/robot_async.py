'''
Actual implementation of the Robot Framework extension
It uses quite extensivle monkey patching as Robot Framework is not
prepared for multi threaded execution of keywords

Just saying this, it is not guaranteed that it will work under all
circumstances or for older or newer version that we are using it for
'''
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
from scoped_value import scope_parameter, _UNDEFINED
from protected_ordered_dict import ProtectedOrderedDict


class Postpone:
    '''
    wrapper which is used when tracing into the xml journal
    in oder to prevent that the file will corrupted.

    The tracing is delayed(postponed) until the moment, that the keyword
    is waited upon in the main thread
    '''
    def __init__(self):
        self._lock = threading.Lock()
        self._postponed = {}
        self._id = threading.local()
        self._next = 0

        self._context = BuiltIn()._get_context()    # noqa, E501  pylint: disable=protected-access
        output = getattr(self._context, 'output', None)
        xmlloggeradapter = getattr(output, '_xml_logger', None)
        if xmlloggeradapter:
            xmllogger = getattr(xmlloggeradapter, 'logger', None)
        else:
            xmllogger = getattr(output, '_xmllogger', None)
        getattr(xmllogger, '_writer', None)
        writer = getattr(xmllogger, '_writer', None)
        if writer:
            writer.start = self.postpone(writer.start)
            writer.end = self.postpone(writer.end)
            writer.element = self.postpone(writer.element)

    def fork(self):
        '''
        Create a new id for capturing traces which belong together.
        The new Id is not activated in any thread though.
        '''
        with self._lock:
            postpone_id = self._next
            self._next += 1
        return postpone_id

    def activate(self, postpone_id):
        '''
        Activate new capture id for the current thread.
        '''
        with self._lock:
            self._postponed[postpone_id] = []
        self._id.value = postpone_id

    def deactivate(self):
        '''
        Deactivate the capture id.
        '''
        try:
            del self._id.value
        except AttributeError:
            pass

    def get(self):
        '''
        return the current active thread id.
        '''
        try:
            return getattr(self._id, 'value')
        except AttributeError:
            return None

    def postpone(self, func):
        '''
        decorator around the original function.
        In case, an postpone Id is activated for the thread,
        just collect the execution with it's parameters
        so it can be done once it is save to do so
        (once we are in main thread)
        '''
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
        '''
        replay all captured commands as it should be save to execute
        them now
        '''
        while True:
            with self._lock:
                try:
                    func = self._postponed[postpone_id].pop(0)
                except IndexError:
                    del self._postponed[postpone_id]
                    break

            func[0](*func[1], **func[2])

    def close(self):
        '''
        undo the monkey patching as the object will get destroyed now
        '''
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


logger_scope = scope_parameter(
    LOGGER,
    '_started_keywords',
    forkvalue=0,
)

CONSOLE_LOGGER_SCOPE = None
if LOGGER._console_logger:    # pylint: disable=protected-access
    try:
        CONSOLE_LOGGER_SCOPE = scope_parameter(
            LOGGER._console_logger.logger,    # noqa, E501  pylint: disable=protected-access
            '_started_keywords',
            forkvalue=0,
        )
    except AttributeError:
        pass


class ScopedContext:
    '''
    collection of things in RobotFramework which
    needs to have different values for threads
    executing Robot Framework keywords ouside of the
    main thread
    This class creates a scope objectes for all of these objects,
    and provides methods which help to create an actual execution
    scope for threads and activation and deactivation methodes
    '''
    _attributes = [
        ['test'],
        [['user_keywords'], []],
        [['step_types'], ['steps']],
        ['timeout_occurred'],
        ['namespace', 'variables', '_scopes'],
        ['namespace', 'variables', '_variables_set', '_scopes'],
        [['_started_keywords'], []],
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
        self._context = BuiltIn()._get_context()    # noqa, E501  pylint: disable=protected-access
        self._forks = []
        for index, attributelist in reversed(
                tuple(enumerate(self._attributes))):
            if not isinstance(attributelist[0], list):
                attributelist = [attributelist]
            for count, attribute in reversed(tuple(enumerate(attributelist))):
                if not attribute:
                    del self._attributes[index]
                    break
                current = self._context
                try:
                    for parameter in attribute:
                        parent = current
                        current = getattr(parent, parameter)
                except AttributeError:
                    if count <= 0:
                        raise
                    continue
                forkvalue = self._construct.get(parameter, _UNDEFINED)    # noqa, E501  pylint: disable=undefined-loop-variable
                scope = scope_parameter(
                    parent, parameter, forkvalue=forkvalue    # noqa, E501  pylint: disable=undefined-loop-variable
                )
                if not isinstance(self._context.namespace._kw_store.libraries,
                                  ProtectedOrderedDict):
                    self._context.namespace._kw_store.libraries = (
                        ProtectedOrderedDict(
                            self._context.namespace._kw_store.libraries
                        )
                    )
                self._forks.append(scope.fork())
                self._attributes[index] = attribute
                break

        self._logger = logger_scope.fork()
        if CONSOLE_LOGGER_SCOPE:
            self._console_logger = CONSOLE_LOGGER_SCOPE.fork()

    def activate(self):
        '''
        activate all scopes for the handled object for current thread
        '''
        forks = self._forks

        for attibute, context in zip(self._attributes, forks):
            current = self._context
            for parameter in attibute[0:-1]:
                current = getattr(current, parameter)
            scope = getattr(current, f'_scoped_{attibute[-1]}')
            scope.activate(context)

        logger_scope.activate(self._logger)
        if CONSOLE_LOGGER_SCOPE:
            CONSOLE_LOGGER_SCOPE.activate(
                self._console_logger
            )

    def kill(self):
        '''
        kill the scopes of all handled objects
        '''
        forks = self._forks
        self._forks = []
        for attibute, context in zip(self._attributes, forks):
            if context is not None:
                current = self._context
                for parameter in attibute[0:-1]:
                    current = getattr(current, parameter)
                scope = getattr(current, f'_scoped_{attibute[-1]}')
                scope.kill(context)
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
            trace = traceback.TracebackException.from_exception(
                    exc
            )
            for line in trace.format():
                logger.console(line)

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
