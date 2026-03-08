"""
Logging module - colorful terminal output + file logging.
"""
import os, sys, logging

class C:
    if sys.platform == "win32": os.system("color")
    @staticmethod
    def green(t): return f"\033[92m{t}\033[0m"
    @staticmethod
    def red(t): return f"\033[91m{t}\033[0m"
    @staticmethod
    def yellow(t): return f"\033[93m{t}\033[0m"
    @staticmethod
    def blue(t): return f"\033[94m{t}\033[0m"
    @staticmethod
    def cyan(t): return f"\033[96m{t}\033[0m"
    @staticmethod
    def magenta(t): return f"\033[95m{t}\033[0m"
    @staticmethod
    def white(t): return f"\033[97m\033[1m{t}\033[0m"
    @staticmethod
    def bold(t): return f"\033[1m{t}\033[0m"
    @staticmethod
    def dim(t): return f"\033[2m{t}\033[0m"
    @staticmethod
    def bg_green(t): return f"\033[42m\033[97m\033[1m{t}\033[0m"
    @staticmethod
    def bg_red(t): return f"\033[41m\033[97m\033[1m{t}\033[0m"
    @staticmethod
    def bg_blue(t): return f"\033[44m\033[97m\033[1m{t}\033[0m"
    @staticmethod
    def bg_yellow(t): return f"\033[43m\033[97m\033[1m{t}\033[0m"
    @staticmethod
    def pnl(p): return f"\033[92m+${p:.2f}\033[0m" if p >= 0 else f"\033[91m-${abs(p):.2f}\033[0m"
    @staticmethod
    def line(ch="-", n=70): return f"\033[2m{ch * n}\033[0m"
    @staticmethod
    def bar(v, mx=100, w=20):
        f = max(0, min(w, int((v/mx)*w) if mx > 0 else 0))
        c = "\033[92m" if v >= 70 else "\033[93m" if v >= 50 else "\033[91m"
        return f"{c}{'#'*f}\033[2m{'.'*(w-f)}\033[0m"


class ColorFormatter(logging.Formatter):
    FORMATS = {
        logging.DEBUG: "\033[2m%(asctime)s | DEBUG | %(message)s\033[0m",
        logging.INFO: "\033[96m%(asctime)s\033[0m | \033[92mINFO\033[0m  | %(message)s",
        logging.WARNING: "\033[96m%(asctime)s\033[0m | \033[93mWARN\033[0m  | %(message)s",
        logging.ERROR: "\033[96m%(asctime)s\033[0m | \033[91mERROR\033[0m | %(message)s",
    }
    def format(self, record):
        return logging.Formatter(
            self.FORMATS.get(record.levelno, self.FORMATS[logging.INFO]),
            datefmt="%H:%M:%S"
        ).format(record)


def setup_logger(name="TradingBot", log_file="trading.log"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(ColorFormatter())
        logger.addHandler(ch)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
    return logger


log = setup_logger()
