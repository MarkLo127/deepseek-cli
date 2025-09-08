from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def print_help() -> None:
    help_text = """
 Basics:
 Add context: Use @ to specify files for context (e.g., @src/myFile.ts) to target specific files or folders.
 Shell mode: Execute shell commands via ! (e.g., !npm run start) or use natural language (e.g. start server).

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
 CLI Version                  0.1.0
 Git Commit                   N/A
 Model                        deepseek-chat
 Sandbox                      no sandbox
 OS                           darwin
 Auth Method                  api_key
"""
    console.print(Panel(Text(about_text.strip(), style="white"), title="About DeepSeek CLI", border_style="blue"))

def print_quit_summary() -> None:
    summary_text = """
 Agent powering down. Goodbye!

 Interaction Summary
 Session ID:                 N/A
 Tool Calls:                 0 ( ✓ 0 x 0 )
 Success Rate:               0.0%

 Performance
 Wall Time:                  0m 0s
 Agent Active:               0s
   » API Time:               0s (0.0%)
   » Tool Time:              0s (0.0%)

 Model Usage                  Reqs   Input Tokens  Output Tokens
 ───────────────────────────────────────────────────────────────
 deepseek-chat                  0         0            0
"""
    console.print(Panel(Text(summary_text.strip(), style="white")))
