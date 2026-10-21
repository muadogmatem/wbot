import os
import importlib
import traceback
from .logger import log_info, log_warn, log_error, C


def load_commands(cmd_dir, module_prefix, registry, engine):
    registered_names = set(registry.names())
    count = 0

    def _scan(directory, prefix):
        nonlocal count

        if not os.path.isdir(directory):
            return

        for f in sorted(os.listdir(directory)):
            full = os.path.join(directory, f)

            if os.path.isdir(full):
                init = os.path.join(full, "__init__.py")
                if not os.path.exists(init):
                    try:
                        open(init, "w").close()
                    except Exception:
                        pass
                _scan(full, f"{prefix}.{f}")
                continue

            if f.startswith("_") or not f.endswith(".py"):
                continue

            mod_name = f"{prefix}.{f[:-3]}"
            try:
                mod = importlib.import_module(mod_name)

                if not hasattr(mod, "_ns"):
                    continue

                ns = mod._ns()
                if not ns:
                    continue

                name = ns["name"].lower()
                cls = ns["cls"]

                instance = cls(engine.bot)
                handler = getattr(instance, "handle", None)
                if handler is None or not callable(handler):
                    log_warn(f"  {name}: no callable 'handle' method")
                    continue

                if name in registered_names:
                    engine.bind(name, handler)
                    count += 1
                    log_info(f"  {C.G}✓{C.D} {C.BOLD}{name}{C.D}")
                else:
                    inline_config = {
                        "perm": ns.get("perm", 1),
                        "cd": ns.get("cd", 0),
                        "hidden": ns.get("hidden", False),
                        "on": ns.get("on", True),
                        "alias": ns.get("alias", [])
                    }
                    engine.bind(name, handler, inline_config)
                    count += 1
                    log_info(f"  {C.Y}○{C.D} {C.BOLD}{name}{C.D} (inline config)")

            except Exception as e:
                log_error(f"  ❌ {mod_name}: {e}")
                traceback.print_exc()

    _scan(cmd_dir, module_prefix)
    return count