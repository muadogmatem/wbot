import os
import json


def _rj(p, d=None):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d or {}


def _wj(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


class Registry:

    def __init__(self, path):
        self.path = path
        self.e = {}
        self.a = {}
        self._load()

    def _load(self):
        for c in _rj(self.path, {"commands": []}).get("commands", []):
            n = c["name"].lower()
            self.e[n] = c
            for al in c.get("alias", []):
                self.a[al.lower()] = n

    def save(self):
        _wj(self.path, {"commands": list(self.e.values())})

    def resolve(self, t):
        t = t.lower()
        if t in self.e:
            return t
        return self.a.get(t)

    def get(self, n):
        return self.e.get(n.lower())

    def names(self):
        return list(self.e)

    def visible_names(self):
        result = []
        for n, entry in self.e.items():
            perm = entry.get("perm", 1)
            if isinstance(perm, str):
                if perm == "hidden":
                    continue
                try:
                    perm = int(perm)
                except ValueError:
                    perm = 1
            if perm == 6:
                continue
            result.append(n)
        return result

    def is_hidden(self, n):
        entry = self.get(n)
        if not entry:
            return False
        perm = entry.get("perm", 1)
        if isinstance(perm, str):
            if perm == "hidden":
                return True
            try:
                perm = int(perm)
            except ValueError:
                return False
        return perm == 6

    def set(self, n, key, val):
        e = self.get(n)
        if not e:
            return False
        if key == "alias":
            for old in e.get("alias", []):
                self.a.pop(old.lower(), None)
            e["alias"] = [x.lower() for x in val]
            for x in e["alias"]:
                self.a[x] = n.lower()
        else:
            e[key] = val
        self.save()
        return True