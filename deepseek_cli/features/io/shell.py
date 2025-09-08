import shlex, subprocess
from rich.syntax import Syntax
from rich.console import Console

class ShellRunner:
    def __init__(self, console: Console): self.console = console
    def run(self, cmd: str):
        try:
            p = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
            if p.stdout: self.console.print(Syntax(p.stdout,"bash",theme="ansi_dark", word_wrap=True))
            if p.stderr: self.console.print(Syntax(p.stderr,"bash",theme="ansi_dark", word_wrap=True))
        except Exception as e: self.console.print(f"[red]系統指令錯誤：[/]{e}")
