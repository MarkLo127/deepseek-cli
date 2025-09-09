from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from typer.core import TyperGroup, TyperCommand
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text

from .core.banner import render_banner, ASCII_DEEPSEEK
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


# ──────────── 讓所有 --help 的圖示固定在最上方且只有一次（ANSI 藍色） ────────────
ANSI_BLUE_BOLD = "\033[1;34m"
ANSI_RESET = "\033[0m"

class BannerGroup(TyperGroup):
    def get_help(self, ctx):  # type: ignore[override]
        base = super().get_help(ctx)
        return f"{ANSI_BLUE_BOLD}{ASCII_DEEPSEEK}{ANSI_RESET}\n\n{base}"

class BannerCommand(TyperCommand):
    def get_help(self, ctx):  # type: ignore[override]
        base = super().get_help(ctx)
        return f"{ANSI_BLUE_BOLD}{ASCII_DEEPSEEK}{ANSI_RESET}\n\n{base}"
# ───────────────────────────────────────────────────────────────────────────────


# 根 app
app = typer.Typer(cls=BannerGroup, add_completion=False, no_args_is_help=False)
console = Console()

# 子群組：config（模仿 gemini-cli 的階層）
config_app = typer.Typer(cls=BannerGroup, add_completion=False, no_args_is_help=True)
app.add_typer(config_app, name="config")


def get_client(cfg: dict):
    if OpenAI is None or not cfg.get("api_key"):
        return None
    base_url = (cfg.get("base_url") or DEFAULT_BASEURL).rstrip("/")
    return OpenAI(api_key=cfg["api_key"], base_url=base_url + "/v1")


def _wizard(existing: Optional[dict] = None) -> dict:
    """互動式編輯（提供預設值、不強迫輸入），用於 config edit / 首次初始化。"""
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

    # API Key 可留空：保留原值或空字串
    api_key_default = cfg.get("api_key", "")
    api_key_input = Prompt.ask("API Key（可留空）", default=api_key_default, password=True)
    cfg["api_key"] = api_key_input.strip()

    # Base URL
    base_default = cfg.get("base_url") or DEFAULT_BASEURL
    base_input = Prompt.ask(f"Base URL（預設 {DEFAULT_BASEURL}）", default=base_default)
    cfg["base_url"] = base_input.strip() or DEFAULT_BASEURL

    return cfg


def ensure_config(force: bool = False) -> dict:
    """維持舊行為：首次或強制時走精靈，否則使用現有設定。"""
    current = load_config()
    if (current and not force):
        current = normalize_with_defaults(current)
        save_config(current)
        return current

    cfg = _wizard(current or {})
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

        # @path → 檔案/資料夾
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

    # 可能新增永久授權 → 落盤
    save_config(consent.cfg)


# ─────────────────────────────────────────── Root / Chat / Setup（別名） ───────────────────────────────────────────
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    # 有子指令就不要印（避免重覆）
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
    """[已棄用] 請改用： deepseek config edit"""
    print_banner()
    console.print("[yellow]提示：`deepseek setup` 已棄用，改為 `deepseek config edit`。[/]")
    _ = ensure_config(force=True)
    console.print("[green]已更新設定[/]")


# ─────────────────────────────────────────── Config 子指令（類 gemini-cli） ───────────────────────────────────────────
@config_app.command("show", cls=BannerCommand)
def config_show():
    """顯示目前設定。"""
    print_banner()
    cfg = normalize_with_defaults(load_config() or {})
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


@config_app.command("set", cls=BannerCommand)
def config_set(
    key: str = typer.Argument(..., help="要設定的鍵，例如 model / base_url / api_key"),
    value: str = typer.Argument(..., help="該鍵的新值"),
):
    """以鍵值方式更新設定（非互動式）。"""
    print_banner()
    cfg = normalize_with_defaults(load_config() or {})
    # 允許常見鍵，其他鍵也可寫入（保持彈性）
    cfg[key] = value
    save_config(cfg)
    console.print(f"[green]✓ 已更新[/] {key} = {value}")


@config_app.command("unset", cls=BannerCommand)
def config_unset(
    key: str = typer.Argument(..., help="要刪除的鍵，例如 api_key"),
):
    """刪除某個鍵（例如移除 api_key）。"""
    print_banner()
    cfg = normalize_with_defaults(load_config() or {})
    if key in cfg:
        # 刪掉之後回到預設行為（例如 base_url 會由 normalize 填預設）
        cfg.pop(key)
        cfg = normalize_with_defaults(cfg)
        save_config(cfg)
        console.print(f"[green]✓ 已移除[/] {key}")
    else:
        console.print(f"[yellow]{key} 不存在，無變更[/]")


@config_app.command("edit", cls=BannerCommand)
def config_edit():
    """互動式設定精靈（取代 setup）。"""
    print_banner()
    current = load_config() or {}
    cfg = _wizard(current)
    # 額外：是否重置已同意的權限旗標
    if any(k in current for k in ("allow_shell", "allow_fs_read", "allow_fs_write")):
        if Confirm.ask("是否清除先前的權限同意？", default=False):
            cfg.pop("allow_shell", None)
            cfg.pop("allow_fs_read", None)
            cfg.pop("allow_fs_write", None)
    save_config(cfg)
    console.print("[green]✓ 設定已儲存[/]")


if __name__ == "__main__":
    app()