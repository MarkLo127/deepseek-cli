from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import click
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text

from .core.banner import ASCII_DEEPSEEK, render_banner
from .core.config import (
    load_config,
    save_config,
    normalize_with_defaults,
    DEFAULT_BASEURL,
    DEFAULT_MODEL,
    SUPPORTED_MODELS,
)
from .core.consent import ConsentManager
from .core.completer import enable_tab_completion
from .core.chat import model_say
from .tool.shell import ShellRunner
from .tool.fs import FileManager

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


console = Console()
app = typer.Typer(add_completion=False, add_help_option=False, no_args_is_help=False)
config_app = typer.Typer(add_completion=False, add_help_option=False, no_args_is_help=True)
app.add_typer(config_app, name="config")

ANSI_BLUE_BOLD = "\033[1;34m"
ANSI_RESET = "\033[0m"


# ────────────── Banner 管理 ──────────────
class BannerManager:
    @staticmethod
    def print_banner() -> None:
        console.print(render_banner())

    @staticmethod
    def print_help_top_and_exit() -> None:
        ctx = click.get_current_context(silent=True)
        click.echo(f"{ANSI_BLUE_BOLD}{ASCII_DEEPSEEK}{ANSI_RESET}\n")
        if ctx is not None and ctx.command is not None:
            click.echo(ctx.get_help())
        raise typer.Exit(0)


# ────────────── Config 管理 ──────────────
class ConfigManager:
    def __init__(self):
        self.cfg = normalize_with_defaults(load_config() or {})

    def show(self):
        safe = dict(self.cfg)
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

    def set(self, key: str, value: str):
        self.cfg[key] = value
        save_config(self.cfg)
        console.print(f"[green]✓ 已更新[/] {key} = {value}")

    def unset(self, key: str):
        if key in self.cfg:
            self.cfg.pop(key)
            self.cfg = normalize_with_defaults(self.cfg)
            save_config(self.cfg)
            console.print(f"[green]✓ 已移除[/] {key}")
        else:
            console.print(f"[yellow]{key} 不存在，無變更[/]")

    def edit(self):
        current = load_config() or {}
        cfg = self._wizard(current)
        if any(k in current for k in ("allow_shell", "allow_fs_read", "allow_fs_write")):
            if Confirm.ask("是否清除先前的權限同意？", default=False):
                cfg.pop("allow_shell", None)
                cfg.pop("allow_fs_read", None)
                cfg.pop("allow_fs_write", None)
        save_config(cfg)
        console.print("[green]✓ 設定已儲存[/]")

    def _wizard(self, existing: Optional[dict] = None) -> dict:
        cfg = normalize_with_defaults(existing or {})
        console.print(Panel.fit("歡迎使用 [bold blue]DeepSeek CLI[/] 設定精靈。", border_style="blue"))
        console.print("選擇模型（按 Enter 預設 [cyan]deepseek-chat[/]）:")
        console.print("  [bold cyan]1[/]. deepseek-chat")
        console.print("  [bold cyan]2[/]. deepseek-reasoner")
        default_choice = "1" if cfg.get("model", DEFAULT_MODEL) == "deepseek-chat" else "2"
        choice = Prompt.ask("模型編號", default=default_choice).strip()
        if choice not in {"1", "2"}:
            choice = default_choice
        cfg["model"] = SUPPORTED_MODELS[int(choice) - 1]
        api_key_default = cfg.get("api_key", "")
        api_key_input = Prompt.ask("API Key（可留空）", default=api_key_default, password=True)
        cfg["api_key"] = api_key_input.strip()
        base_default = cfg.get("base_url") or DEFAULT_BASEURL
        base_input = Prompt.ask(f"Base URL（預設 {DEFAULT_BASEURL}）", default=base_default)
        cfg["base_url"] = base_input.strip() or DEFAULT_BASEURL
        return cfg


# ────────────── Chat / REPL 管理 ──────────────
class ChatManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.client = self.get_client(cfg)

    def get_client(self, cfg: dict):
        if OpenAI is None or not cfg.get("api_key"):
            return None
        base_url = (cfg.get("base_url") or DEFAULT_BASEURL).rstrip("/")
        return OpenAI(api_key=cfg["api_key"], base_url=base_url + "/v1")

    def repl(self):
        BannerManager.print_banner()
        consent = ConsentManager(console, self.cfg)
        shell = ShellRunner(console)
        fs = FileManager(console)

        enable_tab_completion()
        self._show_hints(self.cfg["model"], self.cfg["base_url"])

        while True:
            try:
                s = Prompt.ask("[bold blue]›[/]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if not s:
                continue
            if s.lower() in {"exit", "quit", ":q"}:
                break
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
            if s.startswith("!"):
                if not consent.ensure("shell"):
                    console.print("[yellow]已取消：需要系統指令權限[/]")
                    continue
                shell.run(s[1:])
                continue
            reply = model_say(self.client, self.cfg["model"], s)
            console.print(Text(reply, style="bold cyan"))

        save_config(consent.cfg)

    def _show_hints(self, model: str, base_url: str) -> None:
        console.print(
            Panel.fit(
                "輸入訊息或指令；支援：\n"
                "  • [bold]@<檔案|資料夾>[/] 顯示內容或清單（需同意：讀取）\n"
                "  • [bold]!<shell>[/] 執行命令（需同意：系統指令）\n"
                "  • [bold]:edit <path>[/] 建立/編輯（需同意：寫入；以 :wq 儲存）\n"
                "  • [bold]:open <path>[/] 只讀開啟（需同意：讀取）\n"
                "  • [bold]:ls <path>[/]   列目錄（需同意：讀取）\n"
                "  • [bold]:rm <path>[/]   刪檔案（需同意：寫入）\n"
                "離開：exit / quit / :q",
                title=f"Model • {model}   Base • {base_url}",
                border_style="blue",
            )
        )


# ────────────── Typer 指令 ──────────────
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    help_: bool = typer.Option(False, "--help", "-h", is_flag=True, is_eager=True),
):
    if help_:
        BannerManager.print_help_top_and_exit()
    if ctx.invoked_subcommand is not None:
        return
    cfg = normalize_with_defaults(load_config() or {})
    ChatManager(cfg).repl()


# Config 子指令
@config_app.command("show", add_help_option=False)
def config_show(
    help_: bool = typer.Option(False, "--help", "-h", is_flag=True, is_eager=True),
):
    if help_:
        BannerManager.print_help_top_and_exit()
    BannerManager.print_banner()
    ConfigManager().show()


@config_app.command("set", add_help_option=False)
def config_set(
    key: str,
    value: str,
    help_: bool = typer.Option(False, "--help", "-h", is_flag=True, is_eager=True),
):
    if help_:
        BannerManager.print_help_top_and_exit()
    BannerManager.print_banner()
    ConfigManager().set(key, value)


@config_app.command("unset", add_help_option=False)
def config_unset(
    key: str,
    help_: bool = typer.Option(False, "--help", "-h", is_flag=True, is_eager=True),
):
    if help_:
        BannerManager.print_help_top_and_exit()
    BannerManager.print_banner()
    ConfigManager().unset(key)


@config_app.command("edit", add_help_option=False)
def config_edit(
    help_: bool = typer.Option(False, "--help", "-h", is_flag=True, is_eager=True),
):
    if help_:
        BannerManager.print_help_top_and_exit()
    BannerManager.print_banner()
    ConfigManager().edit()


if __name__ == "__main__":
    app()