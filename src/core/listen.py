import os
import json


class ListenFilter:
    def __init__(self, listen_file):
        self.path = listen_file
        self._cache = set()
        self._mtime = 0
        self._reload()

    def _reload(self):
        try:
            if os.path.exists(self.path):
                mtime = os.path.getmtime(self.path)
                if mtime != self._mtime:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._cache = set(data.get("groups", []))
                    self._mtime = mtime
            else:
                self._cache = set()
        except Exception:
            pass

    def is_listening(self, thread_id):
        self._reload()
        return str(thread_id) in self._cache