from .termcs import Termcs


def run():
    exit_msg = Termcs().run()
    if exit_msg:
        print(exit_msg)
