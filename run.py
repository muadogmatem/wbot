import os
import sys
import time
import signal
import traceback
from datetime import datetime


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


BANNER = f"""
{CY}{BOLD}
  ╔══════════════════════════════════════════════════╗
  ║                                                  ║
  ║            ⚡  ZALO BOT  v2.0  ⚡               ║
  ║                                                  ║
  ╚══════════════════════════════════════════════════╝
{D}"""


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_cli_args(argv):
    args = set(str(x).strip().lower() for x in (argv or []) if str(x).strip())
    return {
        "ignore_server": "-ign.server" in args,
        "disable_log": "-no.log" in args,
        "no_thread": "-no.thread" in args,
        "debug": "-debug" in args,
    }


def main():
    opts = parse_cli_args(sys.argv[1:])
    
    os.environ["BOT_IS_SERVER"] = "1"
    os.environ["BOT_IGNORE_SERVER"] = "1" if opts["ignore_server"] else "0"
    os.environ["BOT_NO_LOG"] = "1" if opts["disable_log"] else "0"
    os.environ["BOT_DEBUG"] = "1" if opts["debug"] else "0"
    
    print(BANNER)
    print(f"  {DIM}Started at {_ts()}{D}")
    print(f"  {DIM}Python {sys.version.split()[0]}{D}")
    print(f"  {G}[SERVER]{D} Running as server (main bot)")
    
    if opts["disable_log"]:
        print(f"  {Y}[OPT]{D} Logging disabled")
    if opts["ignore_server"]:
        print(f"  {Y}[OPT]{D} Server ignored")
    if opts["no_thread"]:
        print(f"  {Y}[OPT]{D} Thread mode disabled")
    if opts["debug"]:
        print(f"  {Y}[OPT]{D} Debug mode enabled")
    
    print()

    try:
        from src import Bot
    except ImportError as e:
        print(f"  {R}{BOLD}[FATAL]{D} Cannot import Bot: {e}")
        traceback.print_exc()
        sys.exit(1)

    bot = None
    running = True

    def _shutdown(sig, frame):
        nonlocal running
        if not running:
            return
        running = False
        print()
        print(f"  {Y}{BOLD}[STOP]{D}  Signal {sig} received, shutting down...")
        print(f"  {DIM}Stopped at {_ts()}{D}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    retry_delay = 5
    max_retry_delay = 60
    attempt = 0
    use_thread = not opts["no_thread"]

    while running:
        attempt += 1
        try:
            print(f"  {G}{BOLD}[BOOT]{D}  Initializing bot (attempt #{attempt})...")
            bot = Bot()

            try:
                from src.mybot.manager import get_manager
                get_manager().auto_start_all()
            except Exception as e:
                print(f"  {R}[MYBOT]{D} Failed to auto-start sub-bots: {e}")
            

            print(f"  {G}{BOLD}[LIVE]{D}  Bot is now listening")
            print(f"  {DIM}{'─' * 50}{D}")
            print()

            bot.listen(run_forever=True, delay=0, thread=use_thread)

            while running:
                time.sleep(1)

        except KeyboardInterrupt:
            _shutdown(2, None)
            break

        except Exception as e:
            print()
            print(f"  {R}{BOLD}[CRASH]{D}  {e}")
            traceback.print_exc()

            if not running:
                break

            print(f"  {Y}[RETRY]{D}  Reconnecting in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)


if __name__ == "__main__":
    main()