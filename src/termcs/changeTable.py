from typing import Callable, List, Dict
from threading import Lock, Timer
from time import time
import re

from rich.text import Text
from textual.app import ComposeResult
from textual.geometry import Size
from textual.reactive import reactive
from textual.widgets import Static, DataTable, Label

# from textual.containers import Horizontal, Vertical, Container, Grid

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


class ChangeTable(Static):
    """
    fetch market data from Binance into DataTable.
    child widgeds updated by thier respect threads that initialized in on_mount()
    """

    search_pattern = reactive("", init=False)
    table_height = reactive(0)
    full_table = reactive(False)
    show_pair = reactive(False)

    asset_count = reactive(0)
    update_eta = reactive(0)

    def __init__(self) -> None:
        super().__init__()
        self.worker = Worker(thresh=60)
        self.lock = Lock()
        self.table = DataTable()
        self.initTable()

    def on_mount(self) -> None:
        self.tableData_thread = RepeatedTimer(1, self.updateTableData)
        self.worker_thread = RepeatedTimer(3, self.updateTable)

    def compose(self) -> ComposeResult:
        yield Label(" ")
        yield Label("0", id="assets")
        yield Label("0", id="eta")
        yield Label(" ")
        yield self.table

    def watch_asset_count(self) -> None:
        self.query_one("#assets", Label).update(f"Assets: {self.asset_count}")

    def watch_update_eta(self) -> None:
        self.query_one("#eta", Label).update(f"Update in: {self.update_eta}")

    def watch_search_pattern(self) -> None:
        self.table.clear(True)
        self.initTable(False)

    # def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
    #     """called on Resize event"""
    #     return self.table_height + 4

    # def watch_table_height(self, table_height: int) -> None:
    #     self.set_timer(0.3, self.forceResizeCall)

    # def forceResizeCall(self) -> None:
    #     """trigger Resize event for the widget if called with set_timer"""
    #     self.styles.display = "none"
    #     self.styles.display = "block"
    #

    def initTable(self, req=True) -> None:
        """
        initialize an empty table

        Args:
            req(bool): if True fetch new data from the API, otherwise use previous cached data
        """
        self.col_keys = self.table.add_columns(
            *[
                "Pair" if self.show_pair else "Asset",
                "Price",
                "Change",
                "High",
                "Low",
                "High change",
                "Low change",
                "Volume",
            ]
        )

        if req:
            self.worker.getAll()
            self.worker.sortBuff()

        table = list(self.worker.buff.values())
        table = table if self.full_table else [*table[:15], *table[-15:]]
        table = self.filt(table, self.search_pattern)

        for asset in table:
            self.table.add_row(*self.assetToRow(asset), key=asset["symbol"])

    def updateTableData(self) -> None:
        """
        Since this function is invoked every second,
        it's worth checking whether the worker has faced any connectivity problems
        """

        if self.worker.kill:
            self.stop()
            self.app.exit("Connection problem ,check your internet, aborting...")

        self.asset_count = self.worker.asset_count
        eta = int(self.worker.update_time - time())
        self.update_eta = eta if eta > 0 else 0

    def updateTable(self) -> None:
        """update (an initialized) table with new data"""
        self.worker.getAll()
        table = list(self.worker.buff.values())
        table = table if self.full_table else [*table[:15], *table[-15:]]
        table = self.filt(table, self.search_pattern)

        if self.update_eta == 0:
            # sort on stats update
            for asset in table:
                k = asset["symbol"]
                self.table.update_cell(k, self.col_keys[1], asset["price"])
                self.table.update_cell(k, self.col_keys[2], asset["change24"])
                self.table.update_cell(k, self.col_keys[3], asset["high"])
                self.table.update_cell(k, self.col_keys[4], asset["low"])
                self.table.update_cell(k, self.col_keys[5], asset["high_change"])
                self.table.update_cell(k, self.col_keys[6], asset["low_change"])
                self.table.update_cell(k, self.col_keys[7], asset["volume"])
            self.table.sort(self.col_keys[2], reverse=True)

        for asset in table:
            for i, val in enumerate(self.assetToRow(asset)[1:]):
                self.table.update_cell(asset["symbol"], self.col_keys[i + 1], val)

    def assetToRow(self, asset: Dict) -> List:
        """
        Convert the asset data into string or Rich text.
        return a list that will be used as a row for the DataTable.
        """
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

        r = [
            name,
            price,
            change,
            high,
            low,
            high_change,
            low_change,
            f'{asset["volume"]:,}',
        ]

        return r

    def filt(self, table: List[Dict], sp: str) -> List[Dict]:
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
        self.table.clear(True)
        self.initTable(False)

    def setPairTo(self, p: Pair) -> None:
        self.worker.setPairTo(p)
        self.table.clear(True)
        self.initTable()

    def showPair(self) -> None:
        self.show_pair = not self.show_pair
        self.table.clear(True)
        self.initTable(False)

    def stop(self) -> None:
        self.active = False
        self.worker_thread.stop()
        self.tableData_thread.stop()
