from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static


class Clock(Widget):
    def on_mount(self) -> None:
        self.set_interval(1, callback=self.refresh, name=f"update header clock")

    def render(self) -> Text:
        return Text(datetime.now().strftime("%X"))


class TopWidget(Widget):
    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("$", id="icon"),
            Static(f"{self.app.TITLE}", id="app-title"),
            Clock(),
        )
