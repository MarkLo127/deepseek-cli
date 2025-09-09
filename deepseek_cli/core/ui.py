from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def print_help() -> None:
    help_text = """
 Basics:

  Commands:
  /about - 關於 deepseek-cli
  /clear - 清除螢幕
  /help - 顯示
  /quit|exit|q - 顯示
  ! - shell 命令行

 Ctrl+C - 結束應用程式
"""
    console.print(Panel(Text(help_text.strip(), style="white"), title="Help", border_style="blue"))

def print_about() -> None:
    about_text = """
 版本                  0.3.0
 模型                  deepseek
"""
    console.print(Panel(Text(about_text.strip(), style="white"), title="About DeepSeek CLI", border_style="blue"))

def print_quit_summary() -> None:
    summary_text = """
 DeepSeek 已退出，掰掰！
"""
    console.print(Panel(Text(summary_text.strip(), style="white"), title="Session Summary", border_style="blue"))
