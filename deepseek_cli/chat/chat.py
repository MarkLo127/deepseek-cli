from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

def model_say(client, model: str, prompt: str) -> str:
    if client is None:
        return f"(離線) {prompt}"
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"(呼叫失敗：{e})"

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from ..core.ui import print_quit_summary

def model_say(client, model: str, prompt: str) -> str:
    if client is None:
        return f"(離線) {prompt}"
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"(呼叫失敗：{e})"

def chat_loop(console: Console, model: str, client, base_url: str) -> None:
    console.print(Panel(f"Chatting with {model}", border_style="blue", expand=False))

    while True:
        try:
            s = Prompt.ask("  >").strip()
            console.print(Panel(f"  > {s}", border_style="blue", expand=False))
        except (EOFError, KeyboardInterrupt):
            console.print()
            print_quit_summary()
            break
        if not s:
            continue

        if s.lower().startswith("/"):
            command = s.lower().split()[0]
            if command == "/quit" or command == "/exit":
                print_quit_summary()
                break
            elif command == "/clear":
                console.clear()
                console.print(Panel(f"Chatting with {model}", border_style="blue", expand=False))
                continue
            else:
                console.print(f"[red]Unknown command: {command}[/red]")
                continue

        if s.lower() in {"exit", "quit", "q"}:
            print_quit_summary()
            break

        with console.status("[bold green]DeepSeek thinking...[/]"):
            reply = model_say(client, model, s)
        console.print(Panel(f"✦ {reply}", border_style="magenta", expand=False))
