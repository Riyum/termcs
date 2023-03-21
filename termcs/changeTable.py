from typing import List, Dict
from time import time
import re

from rich.text import Text
from textual.app import ComposeResult
from textual.geometry import Size
from textual.reactive import reactive
from textual.widgets import Static, DataTable, Label

# from textual.containers import Horizontal, Vertical, Container, Grid

from .worker import STATS_WEIGHT, TERMCS_WEIGHT, WEIGHT_LIMIT, Pair, Worker
from .utils import RepeatedTimer


class ChangeTable(Static):
    """
    fetch market data from Binance into DataTable.
    child widgets updated by their respect threads that initialized in on_mount()
    """

    search_pattern = reactive("", init=False)
    full_table = reactive(False)
    show_pair = reactive(False)

    asset_count: reactive[int] = reactive(0)
    update_eta: reactive[int] = reactive(0)

    width: int = 0

    def __init__(self) -> None:
        super().__init__()
        self.worker = Worker(thresh=60)
        self.table = DataTable(zebra_stripes=True)
        self.initTable()

    def on_mount(self) -> None:
        self.tableData_thread = RepeatedTimer(1, self.updateTableStats)
        # self.worker_thread = RepeatedTimer(3, self.updateTable)

    def compose(self) -> ComposeResult:
        yield Label("0", id="asset_count_label")
        yield Label("0", id="eta_label")
        yield self.table

    def watch_asset_count(self) -> None:
        self.query_one("#asset_count_label", Label).update(
            f"Assets: {self.asset_count}"
        )

    def watch_update_eta(self) -> None:
        self.query_one("#eta_label", Label).update(f"Update in: {self.update_eta}")

    def watch_search_pattern(self) -> None:
        self.table.clear(True)
        self.initTable(False)

    def get_content_width(self, container: Size, viewport: Size) -> int:
        """Force content width size."""
        if self.full_table and len(self.search_pattern) == 0:
            width = self.width + 5
        else:
            width = self.width

        self.query_one("#asset_count_label", Label).styles.width = width
        self.query_one("#eta_label", Label).styles.width = width

        return width

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

        self.width = 0
        for asset in table:
            row_asset = self.assetToRow(asset)
            self.table.add_row(*row_asset, key=asset["symbol"])
            self.updateWidth(row_asset)

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

        if self.update_eta == 0:
            """sort on stats update"""
            self.table.clear(True)
            self.initTable(False)
            return

        table = list(self.worker.buff.values())
        table = table if self.full_table else [*table[:15], *table[-15:]]
        table = self.filt(table, self.search_pattern)

        self.width = 0
        for asset in table:
            row_asset = self.assetToRow(asset)
            for i, val in enumerate(row_asset[1:]):
                self.table.update_cell(asset["symbol"], self.col_keys[i + 1], val)
            self.updateWidth(row_asset)

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

    def updateWidth(self, row: List):
        """update table width"""
        width = 0
        for col, col_name in zip(row, self.table.ordered_columns):
            if col_name.label.plain == "Volume" and len(col) > 9:
                width += len(col) + 4
            else:
                width += max(len(col), col_name.width) + 2

        self.width = max(self.width, width)
        # print(f"row = {row[0]}, width = {width}, cur_max = {self.width}")

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
        self.tableData_thread.stop()
