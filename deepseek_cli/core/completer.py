import os, readline
from pathlib import Path

def _path_candidates(text: str):
    p = Path(os.path.expanduser(text or "."))
    base = p if p.is_dir() else p.parent
    prefix = "" if p.is_dir() else p.name
    try:
        return [str((base / e.name).expanduser()) + ("/" if e.is_dir() else "")
                for e in base.iterdir() if e.name.startswith(prefix)]
    except Exception:
        return []

def _completion_hook(text, state):
    buf = readline.get_line_buffer().lstrip()
    if buf.startswith("@"):
        cands = ["@" + c for c in _path_candidates(buf[1:])]
        return cands[state] if state < len(cands) else None
    return None

def enable_tab_completion():
    try: readline.parse_and_bind("tab: complete")
    except Exception: pass
    readline.set_completer(_completion_hook)
