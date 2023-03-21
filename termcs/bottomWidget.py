from collections import defaultdict
from typing import Dict

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widget import Widget
from textual.binding import Binding
from textual.widgets import Button, Footer, Input


class MyFooter(Footer):

    """
    Footer override for style
    """

    COMPONENT_CLASSES = {
        "footer--description",
        "footer--key",
        "footer--highlight",
        "footer--highlight-key",
        "footer--pressed",
        "footer--pressed-key",
    }

    _active_keys = reactive(
        {"f": False, "s": False, "t": False, "b": False, "o": True, "p": False},
        always_update=True,
    )

    @property
    def active_keys(self) -> Dict[str, bool]:
        return self._active_keys

    @active_keys.setter
    def active_keys(self, arg: dict) -> None:
        self._active_keys = arg

    def watch__active_keys(self, _active_keys: dict) -> None:
        self._key_text = self.make_key_text()

    def toggleKey(self, key: str) -> None:
        """active key setter & force watch call"""
        if key == "b":
            self.active_keys["b"] = True
            self.active_keys["t"] = False
            self.active_keys["o"] = False
        elif key == "t":
            self.active_keys["b"] = False
            self.active_keys["t"] = True
            self.active_keys["o"] = False
        elif key == "o":
            self.active_keys["b"] = False
            self.active_keys["t"] = False
            self.active_keys["o"] = True
        else:
            self.active_keys[key] = not self.active_keys[key]
        """textual issue #1098, Assign the reactive to itself to force a watch_"""
        self.active_keys = self.active_keys

    def make_key_text(self) -> Text:
        """Create text containing all the keys."""
        base_style = self.rich_style
        text = Text(
            style=self.rich_style,
            no_wrap=True,
            overflow="ellipsis",
            justify="left",
            end="",
        )

        bindings = [
            binding
            for (_namespace, binding) in self.app.namespace_bindings.values()
            if binding.show
        ]

        action_to_bindings = defaultdict(list)
        for binding in bindings:
            action_to_bindings[binding.action].append(binding)

        for action, bindings in action_to_bindings.items():
            binding = bindings[0]
            key_display = (
                binding.key.upper()
                if binding.key_display is None
                else binding.key_display
            )

            hovered = self.highlight_key == binding.key
            try:
                pressed = self.active_keys[binding.key]
            except KeyError:
                pressed = False

            if hovered:
                key_style = self.get_component_rich_style("footer--highlight-key")
                key_des_style = self.get_component_rich_style("footer--highlight")
            else:
                key_style = self.get_component_rich_style("footer--key")
                key_des_style = base_style

            if pressed:
                key_style = self.get_component_rich_style("footer--pressed-key")
                if not hovered:
                    key_des_style = self.get_component_rich_style("footer--pressed")

            key_text = Text.assemble(
                (f" {key_display} ", key_style),
                (f" {binding.description} ", key_des_style),
                meta={
                    "@click": f"app.check_bindings('{binding.key}')",
                    "key": binding.key,
                },
            )
            text.append_text(key_text)
        return text


class BottomWidget(Container):

    toggle_search = reactive(False)

    def compose(self) -> ComposeResult:
        yield Button(id="dummy_button")
        yield Widget(MyFooter(), id="footer")
        yield Input(id="search_input", classes="hidden")

    def watch_toggle_search(self, toggle_search: bool) -> None:
        self.query_one("#footer", Widget).set_class(toggle_search, "hidden")
        self.query_one("#search_input", Input).set_class(not toggle_search, "hidden")
        if toggle_search:
            self.query_one("#search_input", Input).focus()
        else:
            self.query_one("#dummy_button", Button).focus()
