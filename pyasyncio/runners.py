__all__ = ('Runner', 'run')

import contextvars
import enum
import functools
import threading
import signal
from . import coroutines
from . import events
from . import exceptions
from . import tasks
from . import constants

class _State(enum.Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    CLOSED = "closed"


class Runner:
    """A context manager that controls event loop life cycle.

    The context manager always creates a new event loop,
    allows to run async functions inside it,
    and properly finalizes the loop at the context manager exit.

    If debug is True, the event loop will be run in debug mode.
    If loop_factory is passed, it is used for new event loop creation.

    pyasyncio.run(main(), debug=True)

    is a shortcut for

    with pyasyncio.Runner(debug=True) as runner:
        runner.run(main())

    The run() method can be called multiple times within the runner's context.

    This can be useful for interactive console (e.g. IPython),
    unittest runners, console tools, -- everywhere when async code
    is called from existing sync framework and where the preferred single
    pyasyncio.run() call doesn't work.

    """

    # Note: the class is final, it is not intended for inheritance.

    def __init__(self, *, debug=None, loop_factory=None):
        # runner状态
        self._state = _State.CREATED
        # debug
        self._debug = debug
        # 事件循环工厂函数
        self._loop_factory = loop_factory
        # 事件循环
        self._loop = None
        # 上下文
        self._context = None
        self._interrupt_count = 0
        # 是否已经设置事件循环
        self._set_event_loop = False

    def __enter__(self):
        self._lazy_init()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Shutdown and close event loop."""
        if self._state is not _State.INITIALIZED:
            return
        try:
            loop = self._loop
            _cancel_all_tasks(loop)
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(
                loop.shutdown_default_executor(constants.THREAD_JOIN_TIMEOUT))
        finally:
            if self._set_event_loop:
                events.set_event_loop(None)
            loop.close()
            self._loop = None
            self._state = _State.CLOSED

    def get_loop(self):
        """Return embedded event loop."""
        self._lazy_init()
        return self._loop

    def run(self, coro, *, context=None):
        """Run a coroutine inside the embedded event loop."""

        # 判定是否是协程
        if not coroutines.iscoroutine(coro):
            raise ValueError("a coroutine was expected, got {!r}".format(coro))

        # 获取运行中的事件循环
        if events._get_running_loop() is not None:
            # fail fast with short traceback
            raise RuntimeError(
                "Runner.run() cannot be called from a running event loop")

        # 事件循环初始化
        self._lazy_init()

        # 设置上下文
        if context is None:
            context = self._context

        # 创建一个task
        # 等同于asyncio.create_task
        task = self._loop.create_task(coro, context=context)

        if (threading.current_thread() is threading.main_thread()
            and signal.getsignal(signal.SIGINT) is signal.default_int_handler
        ):
            sigint_handler = functools.partial(self._on_sigint, main_task=task)
            try:
                signal.signal(signal.SIGINT, sigint_handler)
            except ValueError:
                # `signal.signal` may throw if `threading.main_thread` does
                # not support signals (e.g. embedded interpreter with signals
                # not registered - see gh-91880)
                sigint_handler = None
        else:
            sigint_handler = None

        self._interrupt_count = 0
        try:
            return self._loop.run_until_complete(task)
        except exceptions.CancelledError:
            if self._interrupt_count > 0:
                uncancel = getattr(task, "uncancel", None)
                if uncancel is not None and uncancel() == 0:
                    raise KeyboardInterrupt()
            raise  # CancelledError
        finally:
            if (sigint_handler is not None
                and signal.getsignal(signal.SIGINT) is sigint_handler
            ):
                signal.signal(signal.SIGINT, signal.default_int_handler)

    def _lazy_init(self):
        """
        事件循环初始化
        """
        # runner不能是关闭状态
        if self._state is _State.CLOSED:
            raise RuntimeError("Runner is closed")
        # runner是初始化状态直接就返回
        if self._state is _State.INITIALIZED:
            return

        # 若事件循环工厂函数为None
        if self._loop_factory is None:
            # 创建事件循环
            self._loop = events.new_event_loop()
            if not self._set_event_loop:
                # Call set_event_loop only once to avoid calling
                # attach_loop multiple times on child watchers
                events.set_event_loop(self._loop)
                self._set_event_loop = True
        # 否则调用事件循环工厂函数创建事件循环
        else:
            self._loop = self._loop_factory()
        # 根据runner是否处于debug模式，给事件循环设置debug
        if self._debug is not None:
            self._loop.set_debug(self._debug)
        # 上下文
        self._context = contextvars.copy_context()
        # runner状态从创建转变为初始化完成
        self._state = _State.INITIALIZED

    def _on_sigint(self, signum, frame, main_task):
        self._interrupt_count += 1
        if self._interrupt_count == 1 and not main_task.done():
            main_task.cancel()
            # wakeup loop if it is blocked by select() with long timeout
            self._loop.call_soon_threadsafe(lambda: None)
            return
        raise KeyboardInterrupt()


def run(main, *, debug=None, loop_factory=None):
    """
    执行协程并返回结果
    """

    """Execute the coroutine and return the result.

    This function runs the passed coroutine, taking care of
    managing the pyasyncio event loop, finalizing asynchronous
    generators and closing the default executor.

    当另一个asyncio事件循环在同一个线程中运行时，本函数不能被调用。
    若debug是True，事件循环将在debug模式运行

    This function always creates a new event loop and closes it at the end.
    It should be used as a main entry point for pyasyncio programs, and should
    ideally only be called once.

    The executor is given a timeout duration of 5 minutes to shutdown.
    If the executor hasn't finished within that duration, a warning is
    emitted and the executor is closed.

    Example:

        async def main():
            await pyasyncio.sleep(1)
            print('hello')

        pyasyncio.run(main())
    """
    # 判断当前线程是否已经存在事件循环
    if events._get_running_loop() is not None:
        raise RuntimeError("pyasyncio.run() cannot be called from a running event loop")

    with Runner(debug=debug, loop_factory=loop_factory) as runner:
        return runner.run(main)


def _cancel_all_tasks(loop):
    to_cancel = tasks.all_tasks(loop)
    if not to_cancel:
        return

    for task in to_cancel:
        task.cancel()

    loop.run_until_complete(tasks.gather(*to_cancel, return_exceptions=True))

    for task in to_cancel:
        if task.cancelled():
            continue
        if task.exception() is not None:
            loop.call_exception_handler({
                'message': 'unhandled exception during pyasyncio.run() shutdown',
                'exception': task.exception(),
                'task': task,
            })
