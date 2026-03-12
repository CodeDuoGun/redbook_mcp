HEADLESS = True
BIN_PATH = None


def init_headless(value: bool):
    global HEADLESS
    HEADLESS = value


def set_bin_path(path: str):
    global BIN_PATH
    BIN_PATH = path