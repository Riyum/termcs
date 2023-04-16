import re
from threading import Lock
from time import time
from typing import List

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Label, Static

from .utils import RepeatedTimer, ShutdownMsg
from .worker import QuoteCurrency, RequestType, Worker


class ScreenerTable(Static):
    """
    DataTable filled with market data from Binance.
    child widgets updated by their respect threads that initialized in on_mount()
    """

    search_pattern = reactive("", init=False)
    full_table = reactive(False)
    show_pair = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self.worker = Worker(thresh=60)
        self.table = DataTable(zebra_stripes=True, show_cursor=False)
        self.sort_key = lambda x: x[1]["change24"]  # sort by 24h price change
        self.rev = True
        self.lock = Lock()

    def compose(self) -> ComposeResult:
        yield Vertical(Label("", id="pair_count_label"), classes="screener_label")
        yield Vertical(Label("", id="eta_label"), classes="screener_label")
        yield Vertical(Label("", id="warning_label"), classes="screener_label")
        yield Horizontal(self.table, id="table")

    def on_mount(self) -> None:
        self.fillWorkerBuffer()
        self.initTable()
        self.tableStats_caller = RepeatedTimer(1, self.updateTableStats)
        self.refresh_caller = RepeatedTimer(3, self._refresh)
        self.table.focus()
        self.updateTableStats()

    def watch_search_pattern(self) -> None:
        self.updateTable()

    def on_data_table_header_selected(self, msg: Message) -> None:
        """set the sort key for the selected column and update the table"""
        self.rev = not self.rev
        if msg.column_index == 0:
            self.sort_key = None
        else:
            keys = list(list(self.worker.buff.values())[0])
            self.sort_key = lambda x: x[1][keys[msg.column_index]]

        self.updateTable()

    def fillWorkerBuffer(self):
        with self.lock:
            self.worker.fetchAll()

    def _refresh(self):
        """fetch market data and fill the DataTable"""
        self.fillWorkerBuffer()
        self.app.call_from_thread(self.updateTable)

    def fullTable(self) -> None:
        self.full_table = not self.full_table
        self.updateTable()

    def setQuoteCurrency(self, qc: QuoteCurrency) -> bool:
        if self.worker.setQuoteCurrency(qc):
            self.fillWorkerBuffer()
            self.updateTable()
            return True
        else:
            return False

    def showPair(self) -> None:
        self.show_pair = not self.show_pair
        self.table.clear(True)
        self.initTable()

    def stop(self) -> None:
        self.refresh_caller.stop()
        self.tableStats_caller.stop()

    def updateTableStats(self) -> None:
        """update the labels above the table"""

        # check if the worker encountered any connection errors
        if self.worker.kill:
            self.post_message(
                ShutdownMsg("Connection problem ,check your internet, aborting...")
            )

        if not self.worker.hasWeightFor(RequestType.STATS, user=True):
            self.query_one("#eta_label", Label).styles.margin = (0, 0)
            self.query_one("#warning_label", Label).styles.margin = (0, 0, 1, 0)
            self.query_one("#warning_label", Label).update(
                "!!! CHANGE PAIR RESTRICTION ENABLED !!!"
            )
        else:
            self.query_one("#warning_label", Label).styles.margin = (0, 0)
            self.query_one("#eta_label", Label).styles.margin = (0, 0, 1, 0)
            self.query_one("#warning_label", Label).update()

        self.query_one("#pair_count_label", Label).update(
            f"Pairs: {self.worker.pair_count}"
        )

        eta = int(self.worker.update_time - time())
        self.query_one("#eta_label", Label).update(
            f"Update in: {eta if eta > 0 else 0}s"
        )

    def prepTableData(self) -> List[List]:
        """sort, filter and decorate the pairs data, return a list of DataTable rows"""

        # get a sorted list of the current pairs
        with self.lock:
            pairs = [
                [base_cur, data]
                for base_cur, data in sorted(
                    self.worker.buff.items(), key=self.sort_key, reverse=self.rev
                )
            ]

        # full / mini table
        pairs = pairs if self.full_table else [*pairs[:15], *pairs[-15:]]

        # prep filter pattern
        try:
            pattern = re.compile(self.search_pattern, re.IGNORECASE)
        except re.error:
            pattern = re.compile("")

        # create rows
        rows = []
        for base_cur, data in pairs:

            # filter
            if not pattern.search(base_cur):
                continue

            # decorations
            name = Text(base_cur)
            if self.show_pair:
                name.append(data["quote_cur"], style="#fafab4 italic")

            change = Text(str(data["change24"]))
            change.stylize(
                "green"
                if data["change24"] > 0
                else ("red" if data["change24"] < 0 else "")
            )

            if data["price"] < 10**-4:
                price = f'{data["price"]:.8f}'
                high = f'{data["high"]:.8f}'
                low = f'{data["low"]:.8f}'
            else:
                price = repr(data["price"])
                high = repr(data["high"])
                low = repr(data["low"])

            low_change = repr(data["low_change"])
            high_change = repr(data["high_change"])

            rows.append(
                [
                    name,
                    price,
                    change,
                    high,
                    low,
                    high_change,
                    low_change,
                    f'{data["volume"]:,}',
                ]
            )

        return rows

    def updateTable(self):
        """update the DataTable with new data"""
        pairs = self.prepTableData()
        data_order = [str(k[0]) for k in pairs]
        table_order = [k.value for k in self.table.rows.keys()]

        # reinitialize the rows on sort diff
        if data_order != table_order:
            self.table.clear()
            for pair in pairs:
                self.table.add_row(*pair, key=str(pair[0]))
            return

        for pair in pairs:
            row_k = str(pair[0])
            for data, col_k in zip(pair[1:], list(self.table.columns.keys())[1:]):
                self.table.update_cell(row_k, col_k, data)

    def initTable(self):
        """fill an empty DataTable"""
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
        for pair in self.prepTableData():
            self.table.add_row(*pair, key=str(pair[0]))
