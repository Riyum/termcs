from textual.app import App
from typing import Union

from .screener import Screener
from .utils import RepeatedTimer


class Termcs(App[Union[str, None]]):

    CSS_PATH = "termcs.css"
    SCREENS = {"screener": Screener()}
    TITLE = "Termcs"

    def on_mount(self) -> None:
        self.push_screen("screener")
        self.refresh_table_caller = RepeatedTimer(1, self.refreshTable)

    def refreshTable(self) -> None:
        self.call_from_thread(self.SCREENS["screener"].refreshTable)

    async def action_quit(self) -> None:
        self.refresh_table_caller.stop()
        self.exit()


def run():
    exit_msg = Termcs().run()
    if exit_msg:
        print(exit_msg)
