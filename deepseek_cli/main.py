from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Optional, List, Tuple, Dict

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
from .core.chat import chat_loop, model_say  # 仍沿用你的 chat.py；此處只用 model_say
from .tool.shell import ShellRunner
# FileManager 仍保留，但本檔案直接以 Path 開檔，避免打印到畫面
from .tool.fs import FileManager

from openai import OpenAI
OpenAI = None  # type: ignore


console = Console()
app = typer.Typer(add_completion=False, add_help_option=False, no_args_is_help=False)
config_app = typer.Typer(add_completion=False, add_help_option=False, no_args_is_help=True)
app.add_typer(config_app, name="config")

ANSI_BLUE_BOLD = "\033[1;34m"
ANSI_RESET = "\033[0m"

# ───────────────────────────── Banner/Help ─────────────────────────────
class BannerManager:
    @staticmethod
    def print_banner() -> None:
        console.print(render_banner())

    @staticmethod
    def print_help_top_and_exit() -> None:
        """將 Logo 固定置頂，再輸出目前命令說明。"""
        ctx = click.get_current_context(silent=True)
        click.echo(f"{ANSI_BLUE_BOLD}{ASCII_DEEPSEEK}{ANSI_RESET}\n")
        if ctx is not None and ctx.command is not None:
            click.echo(ctx.get_help())
        raise typer.Exit(0)


# ───────────────────────────── 設定 ─────────────────────────────
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


# ───────────────────────────── 聊天 / REPL（含 @檔案 與 !shell） ─────────────────────────────
WRITE_BLOCK_RE = re.compile(r"<<<WRITE\s+(.+?)\n(.*?)\n>>>END", re.DOTALL)
AT_MENTION_RE = re.compile(r"@([^\s]+)")  # 連續非空白視為路徑（支援相對/含副檔名）

class ChatManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.client = self._get_client(cfg)
        self.consent = ConsentManager(console, self.cfg)
        self.shell = ShellRunner(console)
        # self.fs = FileManager(console)  # 不用它的打印，直接以 Path 處理

    def _get_client(self, cfg: dict):
        if OpenAI is None or not cfg.get("api_key"):
            return None
        base_url = (cfg.get("base_url") or DEFAULT_BASEURL).rstrip("/")
        return OpenAI(api_key=cfg["api_key"], base_url=base_url + "/v1")

    # ---------------------- 解析/處理 @標注 ----------------------
    def _expand_at_mentions(self, s: str) -> List[Path]:
        """抓出訊息中所有 @路徑，轉為 Path（不檢查存在）。"""
        paths: List[Path] = []
        for m in AT_MENTION_RE.finditer(s):
            raw = m.group(1)
            p = Path(os.path.expanduser(raw))
            paths.append(p)
        return paths

    def _read_files_for_context(self, paths: List[Path]) -> Dict[Path, str]:
        """讀取檔案內容供模型參考（需讀取同意）。不存在的檔案會略過。"""
        contents: Dict[Path, str] = {}
        if not paths:
            return contents
        if not self.consent.ensure("fs_read"):
            console.print("[yellow]已取消：需要讀取權限[/]")
            return contents
        for p in paths:
            try:
                if p.is_file():
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    contents[p] = text
            except Exception as e:
                console.print(f"[red]讀取失敗[/] {p}: {e}")
        return contents

    def _build_chat_prompt(self, user_msg: str, file_map: Dict[Path, str]) -> str:
        """將 @檔案內容附加到使用者訊息後方，讓模型有完整上下文。"""
        if not file_map:
            return user_msg
        parts = [user_msg, "\n\n[FILES CONTEXT]"]
        for p, txt in file_map.items():
            parts.append(f"\n### {p}\n```text\n{txt}\n```")
        # 指導模型：若要寫檔，請輸出 WRITE 區塊
        parts.append(
            "\n[INSTRUCTION]\n"
            "若需要修改或建立檔案，請輸出以下格式（一次可多個）：\n"
            "<<<WRITE 路徑\n"
            "<完整檔案內容>\n"
            ">>>END\n"
        )
        return "\n".join(parts)

    # ---------------------- 解析/套用 <<<WRITE ... >>>END ----------------------
    def _apply_write_blocks(self, reply: str, allowed_targets: List[Path]) -> None:
        """從模型回覆中擷取寫檔區塊並在同意下寫入；僅允許寫入使用者這次有 @ 標注的目標。"""
        blocks = WRITE_BLOCK_RE.findall(reply)
        if not blocks:
            return

        # 目標白名單：使用者訊息中有 @ 的檔案（安全考量）
        allow_set = {p.resolve() for p in allowed_targets}

        to_write: List[Tuple[Path, str]] = []
        for raw_path, content in blocks:
            target = Path(os.path.expanduser(raw_path)).resolve()
            if target not in allow_set:
                console.print(f"[yellow]略過寫入[/] {target}（未在訊息中 @ 提及）")
                continue
            to_write.append((target, content))

        if not to_write:
            return

        if not self.consent.ensure("fs_write"):
            console.print("[yellow]已取消：需要寫入權限[/]")
            return

        for path, new_text in to_write:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_text, encoding="utf-8")
                console.print(f"[green]✓ 已寫入[/] {path}")
            except Exception as e:
                console.print(f"[red]寫入失敗[/] {path}: {e}")

    # ---------------------- Shell（支援 @ 展開） ----------------------
    def _expand_at_in_shell(self, cmd: str) -> str:
        """把 ! 命令中的 @路徑展開為 shell 安全字串（加引號）。"""
        def repl(m: re.Match) -> str:
            raw = m.group(1)
            p = Path(os.path.expanduser(raw)).resolve()
            # 用 shlex.quote 確保安全
            return shlex.quote(str(p))
        return AT_MENTION_RE.sub(lambda m: repl(m), cmd)

    # ---------------------- REPL 主流程 ----------------------
    def repl(self):
        BannerManager.print_banner()
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

            # 1) Shell：! 開頭 → 展開 @ 然後執行
            if s.startswith("!"):
                if not self.consent.ensure("shell"):
                    console.print("[yellow]已取消：需要系統指令權限[/]")
                    continue
                expanded = self._expand_at_in_shell(s[1:])
                self.shell.run(expanded)
                continue

            # 2) 聊天：擷取 @ 檔案，帶入上下文
            at_paths = self._expand_at_mentions(s)
            file_map = self._read_files_for_context(at_paths)
            prompt = self._build_chat_prompt(s, file_map)
            reply = model_say(self.client, self.cfg["model"], prompt)
            console.print(Text(reply, style="bold cyan"))

            # 3) 依回覆中的 <<<WRITE ...>>>END 寫入（僅允許本次有 @ 的目標）
            self._apply_write_blocks(reply, allowed_targets=at_paths)

        # REPL 結束：若有新的權限旗標，儲存
        save_config(self.consent.cfg)

    def _show_hints(self, model: str, base_url: str) -> None:
        console.print(
            Panel.fit(
                "輸入訊息或指令；支援：\n"
                "  • [bold]@<檔案|資料夾>[/] 於聊天中標注檔案，模型可閱讀其內容\n"
                "  • [bold]!<shell>[/] 執行命令；支援 @ 展開（例：!cat @README.md）\n"
                "  • 若要請模型幫你改檔，可在訊息中描述「遵照 @A 指示去修改 @B」\n"
                "    模型回覆若附：\n"
                "      <<<WRITE 路徑\\n...內容...\\n>>>END\n"
                "    我會在你同意的前提下自動寫入（僅限本輪 @ 過的檔案目標）\n"
                "離開：exit / quit / :q",
                title=f"Model • {model}   Base • {base_url}",
                border_style="blue",
            )
        )


# ───────────────────────────── Typer 指令 ─────────────────────────────
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