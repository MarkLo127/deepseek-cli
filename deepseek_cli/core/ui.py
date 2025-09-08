from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def print_help() -> None:
    help_text = """
 Basics:

  Commands:
  /about - show version info
  /clear - clear the screen and conversation history
  /help - for help on deepseek-cli
  /quit - exit the cli
  ! - shell command

 Keyboard Shortcuts:
 Ctrl+C - Quit application
"""
    console.print(Panel(Text(help_text.strip(), style="white"), title="Help", border_style="blue"))

def print_about() -> None:
    about_text = """
 Version                  0.3.0
 Model                        deepseek-chat
 Auth Method                  api_key,base_url
"""
    console.print(Panel(Text(about_text.strip(), style="white"), title="About DeepSeek CLI", border_style="blue"))

def print_quit_summary() -> None:
    summary_text = """
 DeepSeek is powering down. Goodbye!
"""
    console.print(Panel(Text(summary_text.strip(), style="white"), title="Session Summary", border_style="blue"))
