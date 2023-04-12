from textual.app import App
from typing import Union

from .screener import Screener


class Termcs(App[Union[str, None]]):

    CSS_PATH = "termcs.css"
    SCREENS = {"screener": Screener()}
    TITLE = "Termcs"

    def on_mount(self) -> None:
        self.push_screen("screener")


def run():
    exit_msg = Termcs().run()
    if exit_msg:
        print(exit_msg)
