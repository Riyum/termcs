from time import sleep

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input
from textual.containers import Vertical

from .utils import RepeatedTimer
from .bottomWidget import BottomWidget, MyFooter
from .changeTable import ChangeTable
from .topWidget import TopWidget
from .worker import Pair


class MainScreen(Screen):

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
        yield Vertical(ChangeTable(), id="center_wrapper")
        yield BottomWidget()

    async def action_quit(self) -> None:
        self.query_one(ChangeTable).stop()
        self.app.exit()

    async def action_full_table(self) -> None:
        self.query_one(BottomWidget).query_one(MyFooter).toggleKey("f")
        self.query_one(ChangeTable).fullTable()

    async def action_change_pair(self, p: str) -> None:

        # TODO: move the weight check
        # if not self.worker.hasWeightFor(RequestType.STATS, user=True):
        #     return

        if p == "busd":
            self.query_one(BottomWidget).query_one(MyFooter).toggleKey("b")
            self.query_one(ChangeTable).setPairTo(Pair.BUSD)
        elif p == "usdt":
            self.query_one(BottomWidget).query_one(MyFooter).toggleKey("t")
            self.query_one(ChangeTable).setPairTo(Pair.USDT)
        elif p == "both":
            self.query_one(BottomWidget).query_one(MyFooter).toggleKey("o")
            self.query_one(ChangeTable).setPairTo(Pair.BOTH)

    async def action_show_pair(self) -> None:
        self.query_one(BottomWidget).query_one(MyFooter).toggleKey("p")
        self.query_one(ChangeTable).showPair()

    async def action_search(self) -> None:
        self.query_one(BottomWidget).toggle_search = True

    async def action_reset_focus(self) -> None:
        self.query_one(BottomWidget).toggle_search = False

    def on_input_changed(self, message: Input.Changed) -> None:
        self.query_one(ChangeTable).search_pattern = message.value

    def updateTable(self):
        self.query_one(ChangeTable).updateTable()


class Termcs(App):

    main_screen = MainScreen()
    CSS_PATH = "termcs.css"
    SCREENS = {"main_screen": main_screen}
    TITLE = "Termcs"

    def on_mount(self) -> None:
        self.push_screen("main_screen")
        self.tasker = RepeatedTimer(3, self.updateTable)

    def updateTable(self) -> None:
        self.call_from_thread(self.main_screen.updateTable)


def run():
    exit_msg = Termcs().run()
    if exit_msg:
        print(exit_msg)
