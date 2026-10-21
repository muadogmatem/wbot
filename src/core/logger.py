from datetime import datetime


class C:
    R = "\033[91m"
    G = "\033[92m"
    Y = "\033[93m"
    B = "\033[94m"
    M = "\033[95m"
    CY = "\033[96m"
    W = "\033[97m"
    D = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


def _log(tag, color, msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f" {C.DIM}{now}{C.D}  {color}{C.BOLD}{tag:>8}{C.D}  {msg}")


def log_info(msg):     _log("INFO", C.G, msg)
def log_cmd(msg):      _log("CMD", C.CY, msg)
def log_warn(msg):     _log("WARN", C.Y, msg)
def log_error(msg):    _log("ERROR", C.R, msg)
def log_debug(msg):    _log("DEBUG", C.M, msg)
def log_msg(msg):      _log("MSG", C.B, msg)