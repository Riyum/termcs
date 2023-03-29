from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Input

from .bottomWidget import BottomWidget, MyFooter
from .cryptoTable import CryptoTable
from .topWidget import TopWidget
from .worker import Pair


class Screener(Screen):

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f", "full_table", "Full"),
        ("b", "change_pair('busd')", "BUSD"),
        ("t", "change_pair('usdt')", "USDT"),
        ("o", "change_pair('both')", "Both"),
        ("p", "show_pair", "Pair"),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("escape", "reset_focus", "Focus", False),
    ]

    def compose(self) -> ComposeResult:
        yield TopWidget()
        yield CryptoTable()
        yield BottomWidget()

    async def action_quit(self) -> None:
        self.query_one(CryptoTable).stop()
        await self.app.action_quit()

    async def action_full_table(self) -> None:
        self.query_one(BottomWidget).query_one(MyFooter).toggleKey("f")
        self.query_one(CryptoTable).fullTable()

    async def action_change_pair(self, p: str) -> None:
        table = self.query_one(CryptoTable)
        footer = self.query_one(BottomWidget).query_one(MyFooter)

        if table.hasWeight():
            if p == "busd":
                footer.toggleKey("b")
                table.setPair(Pair.BUSD)
            elif p == "usdt":
                footer.toggleKey("t")
                table.setPair(Pair.USDT)
            elif p == "both":
                footer.toggleKey("o")
                table.setPair(Pair.BOTH)

    async def action_show_pair(self) -> None:
        self.query_one(BottomWidget).query_one(MyFooter).toggleKey("p")
        self.query_one(CryptoTable).showPair()

    async def action_search(self) -> None:
        self.query_one(BottomWidget).toggle_search = True

    async def action_reset_focus(self) -> None:
        self.query_one(BottomWidget).toggle_search = False
        self.query_one(DataTable).focus()

    def on_input_changed(self, message: Input.Changed) -> None:
        self.query_one(CryptoTable).search_pattern = message.value

    def refreshTable(self):
        self.query_one(CryptoTable)._update()
