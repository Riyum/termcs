from threading import Lock
from typing import List, Dict
from time import time
import re

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, DataTable, Label
from textual.containers import Vertical, Horizontal

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
        self.table = DataTable(zebra_stripes=True)
        self.lock = Lock()
        self.initTable()

    def on_mount(self) -> None:
        self.tableStats_caller = RepeatedTimer(1, self.updateTableStats)
        self.worker_caller = RepeatedTimer(3, self.fillWorkerBuffer)

    def compose(self) -> ComposeResult:
        yield Vertical(Label("", id="asset_count_label"), classes="label")
        yield Vertical(Label("", id="eta_label"), classes="label")
        yield Vertical(Label("", id="warning_label"), classes="label")
        yield Horizontal(self.table, id="table")

    def watch_search_pattern(self) -> None:
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

    def sortAssetsList(
        self, assets: List[Dict], key: str = "change24", rev: bool = True
    ) -> List[Dict]:
        return sorted(assets, key=lambda x: x[key], reverse=rev)

    def filt(self, assets: List[Dict], sp: str) -> List[Dict]:
        """Filter the assets by name"""
        if not sp:
            return assets
        try:
            pattern = re.compile(sp.upper())
        except re.error:
            return assets

        return [asset for asset in assets if pattern.search(asset["asset_name"])]

    def hasWeight(self) -> bool:
        """
        used by the parrent widget to check if the stats request
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
            f"Update in: {eta if eta > 0 else 0}"
        )

    def prepTableData(self, assets: List[Dict], sort=False) -> List[Dict]:
        """prepare the data before inserting it to the DataTable"""
        assets = assets if self.full_table else [*assets[:15], *assets[-15:]]
        assets = self.filt(assets, self.search_pattern)
        if sort:
            assets = self.sortAssetsList(assets)

        return assets

    def assetToRow(self, asset: Dict) -> List:
        """
        Convert the asset data into a string or Rich text.
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
            price = repr(asset["price"])
            high = repr(asset["high"])
            low = repr(asset["low"])

        low_change = repr(asset["low_change"])
        high_change = repr(asset["high_change"])

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

        table_data = self.prepTableData(self.worker.getAssets(), sort=True)

        for asset in table_data:
            row_asset = self.assetToRow(asset)
            self.table.add_row(*row_asset, key=asset["symbol"])

    def updateTable(self) -> None:
        """update (an initialized) DataTable"""

        table_data = self.prepTableData(self.worker.getAssets())

        for asset in table_data:
            row_asset = self.assetToRow(asset)
            for i, val in enumerate(row_asset[1:]):
                self.table.update_cell(asset["symbol"], self.col_keys[i + 1], val)

    def _update(self):
        """
        called by a thread from Termcs
        update the DataTable or clean and initialize on stats update
        """
        if self.worker.stats_update:
            self.table.clear(True)
            self.initTable()
        else:
            self.updateTable()
