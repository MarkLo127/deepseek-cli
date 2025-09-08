from pathlib import Path
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

class FileManager:
    def __init__(self, console: Console): self.console = console

    def list_dir(self, path: Path):
        try:
            items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            lines = [("📄 " if p.is_file() else "📁 ")+p.name for p in items]
            self.console.print(Panel.fit("\n".join(lines) or "(空)", title=str(path), border_style="blue"))
        except Exception as e:
            self.console.print(f"[red]無法列出：[/]{e}")

    def read_file(self, path: Path):
        try:
            text = path.read_text(encoding="utf-8")
            lexer = path.suffix.lstrip(".") or "text"
            self.console.print(Syntax(text, lexer, theme="ansi_dark", word_wrap=True))
        except Exception as e:
            self.console.print(f"[red]無法讀取：[/]{e}")

    def edit_file(self, path: Path):
        self.console.print(f"[blue]編輯：{path}[/]（輸入內容；:wq 儲存）")
        lines: List[str] = []
        while True:
            try: line = input()
            except EOFError: break
            if line.strip()==":wq": break
            lines.append(line)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines), encoding="utf-8")
            self.console.print(f"[green]已寫入：{path}[/]")
        except Exception as e:
            self.console.print(f"[red]無法寫入：[/]{e}")

    def remove_file(self, path: Path):
        try:
            if path.is_file():
                path.unlink()
                self.console.print(f"[green]已刪除：{path}[/]")
            else:
                self.console.print("[red]:rm 只支援檔案[/]")
        except Exception as e:
            self.console.print(f"[red]刪除失敗：[/]{e}")
