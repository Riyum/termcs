from typing import Callable, Union
from threading import Timer
from time import time
from textual.message import Message


def getChange(latest: float, ref: float) -> float:
    """calculate price change"""
    if latest - ref == 0:
        return 0

    return round((latest - ref) / ref * 100, 3)


class ShutdownMsg(Message):
    """shutdown message"""

    def __init__(self, exit_msg: Union[None, str] = None) -> None:
        self.exit_msg = exit_msg
        super().__init__()


class RepeatedTimer(object):
    """
    spawn threads every <interval> seconds to execute a <function>

    Args:
        interval(float): amount of seconds before each call
        function(callable): function to be called
    """

    def __init__(self, interval: float, function: Callable, *args, **kwargs) -> None:
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.next_call = time()
        self.start()

    def _run(self) -> None:
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self) -> None:
        if not self.is_running:
            self.next_call += self.interval
            self._timer = Timer(self.next_call - time(), self._run)
            self._timer.daemon = True
            self._timer.start()
            self.is_running = True

    def stop(self) -> None:
        self._timer.cancel()
        self.is_running = False
