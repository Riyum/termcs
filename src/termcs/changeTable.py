import re
from threading import Lock, Timer
from time import time
from typing import Callable, List

from rich.align import Align
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.geometry import Size
from textual.reactive import reactive
from textual.widget import Widget

from .worker import STATS_WEIGHT, TERMCS_WEIGHT, WEIGHT_LIMIT, Pair, Worker


class RepeatedTimer(object):
    """
    call a <function> every <interval> seconds

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


class TableData(Widget):
    """
    show the current number of assets in the table and calculate the ETA of stats update

    Args:
        worker(Worker): Binance API worker instance
    """

    # TODO: deal with resize call if weight limit reached

    def __init__(self, worker: Worker) -> None:
        super().__init__()
        self.worker = worker

    def on_mount(self) -> None:
        self.set_interval(1, self.refresh)

    def render(self) -> RenderableType:

        grid = Table.grid(padding=(0, 1), expand=True)
        grid.add_column("padL", justify="left", width=1)
        grid.add_column("table", justify="center", ratio=1)
        grid.add_column("padR", justify="right", width=1)
        grid.add_row("", "", "")
        grid.add_row("", Text(f"Assets: {self.worker.asset_count}"), "")
        eta = int(self.worker.update_time - time())
        eta = eta if eta > 0 else 0
        grid.add_row("", Text(f"Update in: {eta}s"), "")
        if WEIGHT_LIMIT - TERMCS_WEIGHT - self.worker.used_weight < STATS_WEIGHT:
            grid.add_row(
                "", Text("!!! CHANGE PAIR RESTRICTION ENABLED !!!", style="red"), ""
            )
        grid.add_row("", "", "")

        return grid


class ChangeTable(Widget):
    """
    fetch market data from Binance into Rich table
    for a better performance, widget refresh + self.table update done with a threaded timer
    avoid using self.set_interval(3, self.updateTable)

    Args:
        worker(Worker): Binance API worker instance
    """

    search_pattern = reactive("")
    table_height = reactive(0)
    full_table = reactive(False)
    show_pair = reactive(False)

    def __init__(self, worker: Worker) -> None:
        super().__init__()
        self.worker = worker
        self.table = worker.getAll()
        self.lock = Lock()

    def on_mount(self) -> None:
        self.worker_thread = RepeatedTimer(3, self.updateTable)

    def render(self) -> RenderableType:

        if self.worker.kill:
            self.stop()
            self.app.exit("Internet problems, aborting...")

        table = self.table if self.full_table else [*self.table[:15], *self.table[-15:]]
        table = self.filt(table, self.search_pattern)
        self.table_height = len(table)

        grid = Table.grid(padding=(0, 1), expand=True)
        grid.add_column("padL", justify="left", width=1)
        grid.add_column("table", justify="center", ratio=1)
        grid.add_column("padR", justify="right", width=1)
        grid.add_row(
            "",
            Align.center(self.richTable(table)),
            "",
        )

        return grid

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        """called on Resize event"""
        return self.table_height + 4

    def watch_table_height(self, table_height: int) -> None:
        self.set_timer(0.3, self.forceResizeCall)

    def forceResizeCall(self) -> None:
        """trigger Resize event for the widget if called with set_timer"""
        self.styles.display = "none"
        self.styles.display = "block"

    def updateTable(self) -> None:
        """update & redraw the table"""
        self.lock.acquire()
        self.table = self.worker.getAll()
        self.lock.release()
        self.refresh()

    def filt(self, table: List[dict], sp) -> List[dict]:
        """Filter the table according to a specific pattern"""
        if not sp:
            return table
        try:
            pattern = re.compile(sp.upper())
        except re.error:
            return table

        return [asset for asset in table if pattern.search(asset["asset_name"])]

    def fullTable(self) -> None:
        self.full_table = not self.full_table

    def setPairTo(self, p: Pair) -> None:
        self.worker.setPairTo(p)

    def showPair(self) -> None:
        self.show_pair = not self.show_pair

    def stop(self) -> None:
        self.active = False
        self.worker_thread.stop()

    def richTable(self, table: List[dict]) -> Table:
        """convert list of dicts into rich table"""
        rich_table = Table(
            "Pair" if self.show_pair else "Asset",
            "Price",
            "Change",
            "High",
            "Low",
            "High change",
            "Low change",
            "Volume",
        )

        for asset in table:

            name = asset["asset_name"]
            if self.show_pair:
                name = Text(asset["asset_name"])
                name.append(asset["symbol"][-4:], style="#fafab4 italic")

            change = Text(str(asset["change24"]))
            change.stylize(
                "green"
                if asset["change24"] > 0
                else ("red" if asset["change24"] < 0 else "")
            )

            if asset["price"] < 10**-4:
                price = f'{asset["price"]:.8f}'
                high = f'{asset["high"]:.8f}'
                low = f'{asset["low"]:.8f}'
            else:
                price = str(asset["price"])
                high = str(asset["high"])
                low = str(asset["low"])

            low_change = str(asset["low_change"])
            high_change = str(asset["high_change"])

            rich_table.add_row(
                name,
                price,
                change,
                high,
                low,
                high_change,
                low_change,
                f'{asset["volume"]:,}',
            )

        return rich_table
