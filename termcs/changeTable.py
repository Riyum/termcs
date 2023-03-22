from typing import List, Dict
from time import time
import re

from rich.text import Text
from textual.app import ComposeResult
from textual.geometry import Size
from textual.reactive import reactive
from textual.widgets import Static, DataTable, Label
from textual.containers import Vertical, Horizontal

# from textual.containers import Horizontal, Vertical, Container, Grid

from .worker import STATS_WEIGHT, TERMCS_WEIGHT, WEIGHT_LIMIT, Pair, RequestType, Worker
from .utils import RepeatedTimer


class ChangeTable(Static):
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
        self.initTable()

    def on_mount(self) -> None:
        self.tableStats_thread = RepeatedTimer(1, self.updateTableStats)
        # self.worker_thread = RepeatedTimer(3, self.updateTable)

    def compose(self) -> ComposeResult:
        yield Vertical(Label("", id="asset_count_label"), classes="label")
        yield Vertical(Label("", id="eta_label"), classes="label")
        yield Vertical(Label("", id="warning_label"), classes="label")
        yield Horizontal(self.table, id="table")

    def watch_search_pattern(self) -> None:
        self.table.clear(True)
        self.initTable(False)

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

        table = list(self.worker.buff.values())
        table = table if self.full_table else [*table[:15], *table[-15:]]
        table = self.filt(table, self.search_pattern)
        table = self.sortAssetsList(table)

        for asset in table:
            row_asset = self.assetToRow(asset)
            self.table.add_row(*row_asset, key=asset["symbol"])

    # def fillTableWithRawData(self, table: List[Dict]) -> None:
    #     """fill an empty table with numbers"""
    #     self.table.clear(True)
    #     for asset in table:
    #         row = [
    #             asset["asset_name"],
    #             asset["price"],
    #             asset["change24"],
    #             asset["high"],
    #             asset["low"],
    #             asset["high_change"],
    #             asset["low_change"],
    #             asset["volume"],
    #         ]
    #         self.table.add_row(*row, key=asset["symbol"])

    def sortAssetsList(
        self, assets: List[Dict], key: str = "change24", rev: bool = True
    ) -> List[Dict]:
        return sorted(assets, key=lambda x: x[key], reverse=rev)

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

    def updateTable(self) -> None:
        """update (an initialized) table with new data"""
        self.worker.getAll()

        if int(self.worker.update_time - time()) <= 0:
            """sort on stats update"""
            self.table.clear(True)
            self.initTable(False)
            return

        table = list(self.worker.buff.values())
        table = table if self.full_table else [*table[:15], *table[-15:]]
        table = self.filt(table, self.search_pattern)

        for asset in table:
            row_asset = self.assetToRow(asset)
            for i, val in enumerate(row_asset[1:]):
                self.table.update_cell(asset["symbol"], self.col_keys[i + 1], val)

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
        # self.worker_thread.stop()
        self.tableStats_thread.stop()

    def hasWeight(self) -> bool:
        """check if the stats request can be made"""
        return self.worker.hasWeightFor(RequestType.STATS, user=True)
