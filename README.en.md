# DeepSeek CLI

[中文](README.md) | [English](README.en.md)

![DeepSeek CLI](assets/deepseek_cli.png)

DeepSeek CLI is a command-line tool that provides the ability to **chat with DeepSeek models** and has built-in support for the following features:
- **Secure Authorization Mechanism**: Asks for user consent before executing any system commands or file I/O.
- **Chat Mode**: Interact directly with DeepSeek models, supporting `deepseek-chat` and `deepseek-reasoner`.
- **File and Directory Operations**: Use `@file/folder` or commands (`:edit`, `:open`, `:ls`, `:rm`) to view and manage files.
- **System Command Execution**: Directly input `!command` in the REPL to execute commands as in a terminal.
- **Tab Completion**: Supports auto-completion for paths and filenames, improving operational convenience.

---

## 🚀 Installation

```bash
# Clone the project
git clone https://github.com/MarkLo127/deepseek-cli.git
cd deepseek-cli

# Install
pip install -e .
```

## 🏁 Quick Start

```bash
deepseek
```
