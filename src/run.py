from termcs.termcs import MainScreen
from textual.app import App


class Termcs(App):

    CSS_PATH = "termcs/termcs.css"
    SCREENS = {"main_screen": MainScreen()}
    TITLE = "Termcs"

    def on_mount(self) -> None:
        self.push_screen("main_screen")


if __name__ == "__main__":

    termcs = Termcs()
    exit_msg = termcs.run()

    if exit_msg:
        print(exit_msg)
