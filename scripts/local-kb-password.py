"""Set the reusable password for the local-only knowledge manager."""

from __future__ import annotations

import getpass
import os
from pathlib import Path
import sys

from local_kb_password import password_file, save_password


ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("KB_LOCAL_DATA_DIR", ROOT / "knowledge-data" / "personal-kb")).resolve()


def set_gui() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    result = 1
    window = tk.Tk()
    window.title("设置本地知识库密码")
    window.resizable(False, False)
    form = ttk.Frame(window, padding=24)
    form.pack()
    ttk.Label(form, text="设置一次即可，重启后仍使用这个密码。\n密码只保存在这台电脑上。", justify="left").grid(
        row=0, column=0, columnspan=2, pady=(0, 18), sticky="w",
    )
    entries = []
    for row, label in enumerate(("管理密码", "再次输入"), start=1):
        ttk.Label(form, text=label).grid(row=row, column=0, padx=(0, 12), pady=6, sticky="w")
        entry = ttk.Entry(form, show="*", width=30)
        entry.grid(row=row, column=1, pady=6)
        entries.append(entry)

    def save() -> None:
        nonlocal result
        password, confirmation = (entry.get() for entry in entries)
        if not password:
            messagebox.showerror("请填写密码", "管理密码不能为空。", parent=window)
            return
        if password != confirmation:
            messagebox.showerror("请检查密码", "两次输入不一致，请重新输入。", parent=window)
            return
        try:
            save_password(DATA, password)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=window)
            return
        result = 0
        window.destroy()

    ttk.Button(form, text="保存密码", command=save).grid(row=3, column=1, pady=(18, 0), sticky="e")
    window.bind("<Return>", lambda _event: save())
    entries[0].focus_set()
    window.mainloop()
    return result


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "status":
        print("已设置" if password_file(DATA).is_file() else "未设置")
        return 0
    if action != "set":
        print("用法：python scripts/local-kb-password.py [set [--gui]|status]")
        return 2
    if "--gui" in sys.argv[2:]:
        return set_gui()
    password = getpass.getpass("设置本地管理密码：")
    confirmation = getpass.getpass("再次输入：")
    if password != confirmation:
        print("两次输入不一致。", file=sys.stderr)
        return 1
    save_password(DATA, password)
    print("密码已保存在当前 Windows 用户可解密的本地文件中；以后启动无需重新设置。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
