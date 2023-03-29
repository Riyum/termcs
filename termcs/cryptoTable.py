from threading import Lock
from typing import List
from time import time
import re

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, DataTable, Label
from textual.containers import Vertical, Horizontal
from textual.message import Message

from .worker import STATS_WEIGHT, TERMCS_WEIGHT, WEIGHT_LIMIT, Pair, RequestType, Worker
from .utils import RepeatedTimer


class CryptoTable(Static):
    """
    fetch market data from Binance into DataTable.
    child widgets updated by their respect threads that initialized in on_mount()
    """

    search_pattern = reactive("", init=False)
    full_table = reactive(False)
    show_pair = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self.worker = Worker(thresh=60)
        self.table = DataTable(zebra_stripes=True, show_cursor=False)
        self.sort_col = 3  # 24h change
        self.rev = True
        self.lock = Lock()
        self.initTable()

    def compose(self) -> ComposeResult:
        yield Vertical(Label("", id="asset_count_label"), classes="label")
        yield Vertical(Label("", id="eta_label"), classes="label")
        yield Vertical(Label("", id="warning_label"), classes="label")
        yield Horizontal(self.table, id="table")

    def on_mount(self) -> None:
        self.updateTableStats()
        self.tableStats_caller = RepeatedTimer(1, self.updateTableStats)
        self.worker_caller = RepeatedTimer(3, self.fillWorkerBuffer)
        self.table.focus()

    def watch_search_pattern(self) -> None:
        self.table.clear(True)
        self.initTable()

    def on_data_table_header_selected(self, msg: Message) -> None:
        """sort the table according to a selected column index"""
        self.sort_col = msg.column_index + 1
        self.rev = not self.rev
        self.table.clear(True)
        self.initTable()

    def fillWorkerBuffer(self):
        self.lock.acquire()
        self.worker.fetchAll()
        self.lock.release()

    def fullTable(self) -> None:
        self.full_table = not self.full_table
        self.table.clear(True)
        self.initTable()

    def setPair(self, p: Pair) -> None:
        self.worker.setPair(p)
        self.table.clear(True)
        self.worker_caller.stop()
        self.fillWorkerBuffer()
        self.worker_caller.start()
        self.initTable()

    def showPair(self) -> None:
        self.show_pair = not self.show_pair
        self.table.clear(True)
        self.initTable()

    def stop(self) -> None:
        self.active = False
        self.worker_caller.stop()
        self.tableStats_caller.stop()

    def hasWeight(self) -> bool:
        """
        used by the parent widget to check if the stats request
        can be made by the worker
        """
        return self.worker.hasWeightFor(RequestType.STATS, user=True)

    def updateTableStats(self) -> None:
        """update the labels above the table"""

        """
        Since this function is invoked every second,
        it's worth checking whether the worker has faced any connectivity problems
        """
        if self.worker.kill:
            self.stop()
            self.app.exit("Connection problem ,check your internet, aborting...")

        if WEIGHT_LIMIT - TERMCS_WEIGHT - self.worker.used_weight < STATS_WEIGHT:
            self.query_one("#eta_label", Label).styles.margin = (0, 0)
            self.query_one("#warning_label", Label).styles.margin = (0, 0, 1, 0)
            self.query_one("#warning_label", Label).update(
                "!!! CHANGE PAIR RESTRICTION ENABLED !!!"
            )
        else:
            self.query_one("#warning_label", Label).styles.margin = (0, 0)
            self.query_one("#eta_label", Label).styles.margin = (0, 0, 1, 0)
            self.query_one("#warning_label", Label).update()

        self.query_one("#asset_count_label", Label).update(
            f"Assets: {self.worker.asset_count}"
        )

        eta = int(self.worker.update_time - time())
        self.query_one("#eta_label", Label).update(
            f"Update in: {eta if eta > 0 else 0}s"
        )

    def prepTableData(self, sort: bool = False) -> List[List]:
        """sort, filter and decorate the assets data, return a list of DataTable rows"""

        # sort the data
        if sort:
            keys = list(list(self.worker.buff.values())[0])
            self.worker.sortBuff(keys[self.sort_col], self.rev)

        # get a list of the current assets
        assets = self.worker.getAssets()

        # full / mini table
        assets = assets if self.full_table else [*assets[:15], *assets[-15:]]

        # prep filter
        sp = self.search_pattern
        try:
            pattern = re.compile(sp.upper())
        except re.error:
            pattern = re.compile("")

        # create rows for the DataTable
        rows = []
        for asset in assets:

            # filter
            if not pattern.search(asset["asset_name"]):
                continue

            # decorations
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
                price = repr(asset["price"])
                high = repr(asset["high"])
                low = repr(asset["low"])

            low_change = repr(asset["low_change"])
            high_change = repr(asset["high_change"])

            rows.append(
                [
                    asset["symbol"],
                    name,
                    price,
                    change,
                    high,
                    low,
                    high_change,
                    low_change,
                    f'{asset["volume"]:,}',
                ]
            )

        return rows

    def initTable(self) -> None:
        """initialize an empty DataTable"""
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

        for asset in self.prepTableData(sort=True):
            self.table.add_row(*asset[1:], key=asset[0])

    def updateTable(self) -> None:
        """update (an initialized) DataTable"""
        for asset in self.prepTableData():
            row_key = asset[0]
            for data, col_key in zip(asset[2:], self.col_keys[1:]):
                self.table.update_cell(row_key, col_key, data)

    def _update(self) -> None:
        """
        called by a thread from Termcs
        update the DataTable or clean and initialize on stats update
        """
        if self.worker.stats_update:
            self.table.clear(True)
            self.initTable()
        else:
            self.updateTable()
