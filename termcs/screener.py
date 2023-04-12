from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Input

from .bottomWidget import BottomWidget, MyFooter
from .screenerTable import ScreenerTable
from .topWidget import TopWidget
from .utils import ShutdownMsg
from .worker import QuoteCurrency


class Screener(Screen):

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f", "full_table", "Full"),
        ("b", "set_quote_cur('busd')", "BUSD"),
        ("t", "set_quote_cur('usdt')", "USDT"),
        ("o", "set_quote_cur('both')", "Both"),
        ("p", "show_pair", "Pair"),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("escape", "reset_focus", "Focus", False),
    ]

    def compose(self) -> ComposeResult:
        yield TopWidget()
        yield ScreenerTable()
        yield BottomWidget()

    def action_quit(self) -> None:
        self.post_message(ShutdownMsg())

    async def action_full_table(self) -> None:
        self.query_one(BottomWidget).query_one(MyFooter).toggleKey("f")
        self.query_one(ScreenerTable).fullTable()

    async def action_set_quote_cur(self, qc: QuoteCurrency) -> None:
        table = self.query_one(ScreenerTable)
        footer = self.query_one(BottomWidget).query_one(MyFooter)

        if table.setQuoteCurrency(qc):
            if qc == QuoteCurrency.BUSD.value:
                footer.toggleKey("b")
            elif qc == QuoteCurrency.USDT.value:
                footer.toggleKey("t")
            elif qc == QuoteCurrency.BOTH.value:
                footer.toggleKey("o")

    async def action_show_pair(self) -> None:
        self.query_one(BottomWidget).query_one(MyFooter).toggleKey("p")
        self.query_one(ScreenerTable).showPair()

    async def action_search(self) -> None:
        self.query_one(BottomWidget).toggle_search = True

    async def action_reset_focus(self) -> None:
        self.query_one(BottomWidget).toggle_search = False
        self.query_one(DataTable).focus()

    def on_input_changed(self, message: Input.Changed) -> None:
        self.query_one(ScreenerTable).search_pattern = message.value

    def shutdown(self):
        self.query_one(ScreenerTable).stop()
