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

def chat_loop(console: Console, model: str, client, base_url: str) -> None:
    console.print(
        Panel.fit(
            f"聊天模式\n模型： {model}\nBase URL： {base_url}\n離開：exit / quit / q",
            border_style="blue",
        )
    )
    while True:
        try:
            s = Prompt.ask("[bold blue]›[/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not s:
            continue
        if s.lower() in {"exit", "quit", "q"}:
            break
        console.print(Text(model_say(client, model, s), style="bold cyan"))
