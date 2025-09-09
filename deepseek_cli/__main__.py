from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from typer.core import TyperGroup, TyperCommand  # 必須繼承 Typer 的類，否則會觸發斷言
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from.core.banner import render_banner, ASCII_DEEPSEEK
from .core.config import (
    load_config, save_config, normalize_with_defaults,
    DEFAULT_BASEURL, DEFAULT_MODEL, SUPPORTED_MODELS,
)
from .core.consent import ConsentManager
from .core.completer import enable_tab_completion
from .core.chat import chat_loop, model_say
from .tool.shell import ShellRunner
from .tool.fs import FileManager


from openai import OpenAI
OpenAI = None  # type: ignore



# ──────────── 讓所有 --help 的圖示置頂 & 保持藍色（用 ANSI），且只顯示一次 ────────────
ANSI_BLUE_BOLD = "\033[1;34m"
ANSI_RESET = "\033[0m"

class BannerGroup(TyperGroup):
    def get_help(self, ctx):  # type: ignore[override]
        base = super().get_help(ctx)
        # 直接把圖示前置，避免 RichHelpFormatter 把文字搬到最底
        return f"{ANSI_BLUE_BOLD}{ASCII_DEEPSEEK}{ANSI_RESET}\n\n{base}"

class BannerCommand(TyperCommand):
    def get_help(self, ctx):  # type: ignore[override]
        base = super().get_help(ctx)
        return f"{ANSI_BLUE_BOLD}{ASCII_DEEPSEEK}{ANSI_RESET}\n\n{base}"
# ───────────────────────────────────────────────────────────────────────────────


app = typer.Typer(cls=BannerGroup, add_completion=False)
console = Console()


def get_client(cfg: dict):
    if OpenAI is None or not cfg.get("api_key"):
        return None
    base_url = (cfg.get("base_url") or DEFAULT_BASEURL).rstrip("/")
    return OpenAI(api_key=cfg["api_key"], base_url=base_url + "/v1")


def ensure_config(force: bool = False) -> dict:
    cfg = normalize_with_defaults(load_config())
    if cfg.get("model") and not force:
        save_config(cfg)
        return cfg

    console.print(Panel.fit("歡迎使用 [bold blue]DeepSeek CLI[/]！請完成設定。", border_style="blue"))
    console.print("選擇模型（按 Enter 預設 [cyan]deepseek-chat[/]）:")
    console.print("  [bold cyan]1[/]. deepseek-chat")
    console.print("  [bold cyan]2[/]. deepseek-reasoner")
    choice = Prompt.ask("模型編號", default="1").strip()
    if choice not in {"1", "2"}:
        choice = "1"
    cfg["model"] = SUPPORTED_MODELS[int(choice) - 1]

    api_key = Prompt.ask("請輸入 API Key（可留空）", default="", password=True).strip()
    if api_key:
        cfg["api_key"] = api_key

    base_url = Prompt.ask(
        f"請輸入 Base URL（可留空，預設 {DEFAULT_BASEURL}）", default=""
    ).strip()
    cfg["base_url"] = base_url if base_url else DEFAULT_BASEURL

    save_config(cfg)
    console.print("[green]✓ 設定已儲存[/]")
    return cfg


def print_banner() -> None:
    # 一般執行（非 --help）時用 Rich 藍色
    console.print(render_banner())


def show_hints(model: str, base_url: str) -> None:
    console.print(
        Panel.fit(
            "輸入訊息或指令；支援：\n"
            "  • [bold]@<檔案|資料夾>[/] 顯示內容或清單（需同意：讀取）\n"
            "  • [bold]!<shell>[/] 執行命令（需同意：系統指令）\n"
            "  • [bold]:edit <path>[/] 建立/編輯（需同意：寫入；以 :wq 儲存）\n"
            "  • [bold]:open <path>[/] 只讀開啟（需同意：讀取）\n"
            "  • [bold]:ls <path>[/]   列目錄（需同意：讀取）\n"
            "  • [bold]:rm <path>[/]   刪檔案（需同意：寫入）\n"
            "離開：exit / quit / q",
            title=f"Model • {model}   Base • {base_url}",
            border_style="blue",
        )
    )


def repl_with_tools(cfg: dict) -> None:
    """主 REPL：聊天 + shell + 檔案操作（皆需使用者授權）。"""
    model = cfg.get("model", DEFAULT_MODEL)
    base_url = cfg.get("base_url") or DEFAULT_BASEURL
    client = get_client(cfg)

    consent = ConsentManager(console, cfg)
    shell = ShellRunner(console)
    fs = FileManager(console)

    enable_tab_completion()
    show_hints(model, base_url)

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

        # @path
        if s.startswith("@"):
            if not consent.ensure("fs_read"):
                console.print("[yellow]已取消：需要讀取權限[/]")
                continue
            p = Path(os.path.expanduser(s[1:]))
            if p.is_file():
                fs.read_file(p)
            elif p.is_dir():
                fs.list_dir(p)
            else:
                console.print("[red]找不到檔案或資料夾[/]")
            continue

        # :edit / :open / :ls / :rm
        if s.startswith(":edit "):
            if not consent.ensure("fs_write"):
                console.print("[yellow]已取消：需要寫入權限[/]")
                continue
            fs.edit_file(Path(os.path.expanduser(s.split(" ", 1)[1])))
            continue

        if s.startswith(":open "):
            if not consent.ensure("fs_read"):
                console.print("[yellow]已取消：需要讀取權限[/]")
                continue
            fs.read_file(Path(os.path.expanduser(s.split(" ", 1)[1])))
            continue

        if s.startswith(":ls "):
            if not consent.ensure("fs_read"):
                console.print("[yellow]已取消：需要讀取權限[/]")
                continue
            fs.list_dir(Path(os.path.expanduser(s.split(" ", 1)[1])))
            continue

        if s.startswith(":rm "):
            if not consent.ensure("fs_write"):
                console.print("[yellow]已取消：需要寫入權限，且此動作具破壞性[/]")
                continue
            fs.remove_file(Path(os.path.expanduser(s.split(" ", 1)[1])))
            continue

        # !shell
        if s.startswith("!"):
            if not consent.ensure("shell"):
                console.print("[yellow]已取消：需要系統指令權限[/]")
                continue
            shell.run(s[1:])
            continue

        # 其他 → 當作聊天
        reply = model_say(get_client(cfg), model, s)
        console.print(Text(reply, style="bold cyan"))

    # 落盤記錄可能更新的永久授權
    save_config(consent.cfg)


# ─────────────────────────────────────────── Typer Commands ───────────────────────────────────────────
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    # 若有子指令，不印圖示（避免重複）
    if ctx.invoked_subcommand is not None:
        return
    print_banner()
    cfg = ensure_config()
    repl_with_tools(cfg)


@app.command(cls=BannerCommand)
def chat():
    """單純聊天模式。"""
    print_banner()
    cfg = ensure_config()
    cfg = normalize_with_defaults(cfg)
    client = get_client(cfg)
    chat_loop(console, cfg["model"], client, cfg["base_url"])


@app.command(cls=BannerCommand)
def setup():
    """重新執行設定精靈。"""
    print_banner()
    _ = ensure_config(force=True)
    console.print("[green]已更新設定[/]")


@app.command(cls=BannerCommand)
def config(
    action: str = typer.Argument(..., help="show / set"),
    key: Optional[str] = typer.Option(None),
    value: Optional[str] = typer.Option(None),
):
    """deepseek config show / deepseek config set --key ... --value ..."""
    print_banner()
    cfg = normalize_with_defaults(load_config() or {})
    if action == "show":
        safe = dict(cfg)
        if "api_key" in safe:
            safe["api_key"] = "***"
        console.print(
            Panel.fit(
                Text.from_markup(
                    f"[bold]model:[/]\t{safe.get('model')}\n"
                    f"[bold]base_url:[/]\t{safe.get('base_url')}\n"
                    f"[bold]api_key:[/]\t{safe.get('api_key','')}\n"
                    f"[bold]allow_shell:[/]\t{safe.get('allow_shell', False)}\n"
                    f"[bold]allow_fs_read:[/]\t{safe.get('allow_fs_read', False)}\n"
                    f"[bold]allow_fs_write:[/]\t{safe.get('allow_fs_write', False)}"
                ),
                title="config",
                border_style="blue",
            )
        )
        return

    if action == "set":
        if not key:
            console.print("[red]請提供 --key[/]")
            raise typer.Exit(1)
        if key == "api_key" and value is None:
            value = Prompt.ask("輸入新的 API Key", password=True)
        if value is None:
            console.print("[red]請提供 --value[/]")
            raise typer.Exit(1)
        cfg[key] = value
        save_config(cfg)
        console.print("[green]✓ 已更新[/]")
        return

    console.print("[red]未知動作，僅支援 show / set[/]")


if __name__ == "__main__":
    app()