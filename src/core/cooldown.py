import time
import threading
from concurrent.futures import ThreadPoolExecutor

from .reactions import ReactionManager, REACTIONS

_pool = ThreadPoolExecutor(8)


class CooldownManager:

    def __init__(self, rm: ReactionManager):
        self.rm = rm
        self._lock = threading.Lock()
        self._last = {}
        self._waiting = {}
        self._waiting_lock = threading.Lock()

    def check(self, name, uid, tid, cd_seconds):
        if cd_seconds <= 0:
            return None

        key = f"{name}:{uid}:{tid}"
        with self._lock:
            now = time.time()
            last = self._last.get(key, 0)
            if now - last < cd_seconds:
                return cd_seconds - (now - last)
            self._last[key] = now
            return None

    def mark(self, name, uid, tid):
        key = f"{name}:{uid}:{tid}"
        with self._lock:
            self._last[key] = time.time()

    def countdown_then_run(self, remain, name, fn, msg, mo, tid, tt, uid, run_handler_fn):
        cd_key = f"{name}:{uid}:{tid}"

        with self._waiting_lock:
            if self._waiting.get(cd_key):
                return
            self._waiting[cd_key] = True

        def _run():
            try:
                secs = max(1, min(int(remain) + 1, 500))

                self.rm.multi_react(mo, REACTIONS["cooldown"], secs, tid, tt)

                for i in range(secs):
                    time.sleep(1)
                    remaining = secs - (i + 1)

                    self.rm.remove_react(mo, REACTIONS["cooldown"], tid, tt)

                    if remaining > 0:
                        time.sleep(0.01)  
                        self.rm.multi_react(mo, REACTIONS["cooldown"], remaining, tid, tt)

                self.mark(name, uid, tid)

                self.rm.react(mo, REACTIONS["received"], tid, tt)
                run_handler_fn(fn, name, msg, mo, tid, tt, uid)

            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                with self._waiting_lock:
                    self._waiting.pop(cd_key, None)

        _pool.submit(_run)