from __future__ import annotations
from typing import Literal
from rich.panel import Panel
from rich.prompt import Confirm
from rich.console import Console

ConsentKind = Literal["shell", "fs_read", "fs_write"]

class ConsentManager:
    def __init__(self, console: Console, cfg: dict):
        self.console = console
        self.cfg = cfg
        self.session_cache: dict[str, bool] = {}

    def ensure(self, kind: ConsentKind) -> bool:
        if self.session_cache.get(kind) is True:
            return True
        cfg_key = f"allow_{kind}"
        if self.cfg.get(cfg_key) is True:
            self.session_cache[kind] = True
            return True
        title_map = {
            "shell": "執行系統指令",
            "fs_read": "讀取檔案/資料夾",
            "fs_write": "寫入/修改/刪除檔案",
        }
        self.console.print(Panel.fit(
            f"此操作需要你的同意： [bold]{title_map[kind]}[/]\n你要允許嗎？（僅本次）",
            border_style="yellow"))
        allow_once = Confirm.ask("允許本次？", default=False)
        if not allow_once:
            return False
        remember = Confirm.ask("是否記住同意（永久）？", default=False)
        if remember:
            self.cfg[cfg_key] = True
        self.session_cache[kind] = True
        return True
