#!/usr/bin/env python3
"""Family use-time guard for Raspberry Pi OS Desktop."""
import datetime
import json
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.environ.get("PI_CONTROL_URL", "").rstrip("/")
TOKEN = os.environ.get("PI_DEVICE_TOKEN", "")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
LOCK_FILE = "/tmp/pi-family-control-lock.json"
EXTENSION_OPTIONS = [(5, "5分"), (15, "15分"), (30, "30分"), (60, "1時間"), (120, "2時間"), (180, "3時間")]

def api(path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(BASE + path, data=data, method=method,
                  headers={"X-Device-Token": TOKEN, "Content-Type": "application/json"})
    with urlopen(req, timeout=8) as response:
        return json.loads(response.read().decode())

def now():
    return datetime.datetime.now().astimezone()

def datekey(dt):
    return dt.strftime("%Y-%m-%d")

def in_time(dt, start, end):
    sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":"))
    n, a, b = dt.hour * 60 + dt.minute, sh * 60 + sm, eh * 60 + em
    if a == b: return True
    return a <= n < b if a < b else n >= a or n < b

def allowed(config, dt):
    control = config.get("control", {})
    override = control.get("piOverrideUntil")
    if override:
        try:
            if datetime.datetime.fromisoformat(override.replace("Z", "+00:00")) > dt: return True, "一時解除中"
        except (TypeError, ValueError): pass
    if control.get("manualLock"): return False, "管理サイトから手動ロックされています"
    settings = config.get("settings", {})
    if settings.get("scheduleEnabled"):
        day = config.get("schedule", {}).get(DAYS[dt.weekday()], {})
        if not day.get("enabled") or not in_time(dt, day.get("start", "00:00"), day.get("end", "00:00")): return False, "利用できる時間帯の外です"
    limit = settings.get("dailyLimitMinutes")
    if limit is not None:
        used = int((config.get("usage", {}).get("daily", {}).get(datekey(dt)) or {}).get("seconds", 0))
        extra = int(control.get("todayExtensionMinutes", 0)) if control.get("extensionDate") == datekey(dt) else 0
        if used >= (int(limit) + extra) * 60: return False, "今日の使用上限に達しました"
    return True, "利用できます"

def report(seconds):
    if seconds <= 0: return
    try: api("/api/device-report", "POST", {"date": datekey(now()), "seconds": min(120, int(seconds))})
    except Exception as exc: print("usage report:", exc, flush=True)

def worker():
    total = 0; last = last_report = time.monotonic()
    while True:
        current = time.monotonic(); delta = max(0, min(20, current - last)); last = current
        try: config = api("/api/device-state")
        except Exception as exc:
            print("cloud error:", exc, flush=True)
            config = {"settings": {"scheduleEnabled": True, "dailyLimitMinutes": 1}, "control": {"manualLock": True}}
        permitted, reason = allowed(config, now())
        if permitted: total += delta
        if current - last_report >= 60: report(total); total = 0; last_report = current
        try:
            if permitted:
                if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)
            else:
                with open(LOCK_FILE, "w", encoding="utf-8") as stream: json.dump({"reason": reason}, stream)
        except OSError: pass
        time.sleep(10)

def shutdown():
    if messagebox.askyesno("確認", "ラズパイをシャットダウンしますか？"): os.system("systemctl poweroff")

def extend_from_pi(root):
    password = simpledialog.askstring("パスワードで解除", "管理パスワードを入力してください:", show="*", parent=root)
    if password is None: return
    choice = tk.Toplevel(root); choice.title("解除時間"); choice.configure(bg="#101827")
    choice.transient(root); choice.grab_set(); choice.resizable(False, False)
    tk.Label(choice, text="解除する時間を選んでください", font=("Sans", 15), fg="white", bg="#101827").pack(padx=24, pady=(18, 10))
    result = {"minutes": None}; buttons = tk.Frame(choice, bg="#101827"); buttons.pack(padx=16, pady=(0, 16))
    def choose(minutes): result["minutes"] = minutes; choice.destroy()
    for minutes, label in EXTENSION_OPTIONS:
        column = (minutes - 5) // 10 if minutes < 60 else (minutes // 60) - 1
        tk.Button(buttons, text=label, font=("Sans", 13), width=9, command=lambda m=minutes: choose(m)).grid(row=0 if minutes < 60 else 1, column=column, padx=5, pady=5)
    choice.wait_window()
    if result["minutes"] is None: return
    try:
        api("/api/device-extend", "POST", {"password": password, "minutes": result["minutes"]})
        messagebox.showinfo("一時解除", f"{dict(EXTENSION_OPTIONS)[result['minutes']]}間、利用できます。", parent=root)
    except HTTPError as exc:
        try: detail = json.loads(exc.read().decode()).get("error", "通信に失敗しました")
        except Exception: detail = "通信に失敗しました"
        messagebox.showerror("解除できません", detail, parent=root)
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        messagebox.showerror("通信エラー", f"サーバーに接続できません。\n{exc}", parent=root)

def show_locked(root, reason):
    root.configure(bg="#101827")
    for child in root.winfo_children(): child.destroy()
    frame = tk.Frame(root, bg="#101827"); frame.place(relx=.5, rely=.5, anchor="center")
    tk.Label(frame, text="利用できません", font=("Sans", 30, "bold"), fg="white", bg="#101827").pack(pady=12)
    tk.Label(frame, text=reason, font=("Sans", 15), fg="white", bg="#101827", wraplength=650).pack(pady=10)
    tk.Label(frame, text="パスワードを入力して一時解除できます", font=("Sans", 12), fg="#ccd5e2", bg="#101827").pack(pady=8)
    tk.Button(frame, text="パスワードでロック解除・延長", font=("Sans", 14), command=lambda: extend_from_pi(root), width=30).pack(pady=10)
    tk.Button(frame, text="シャットダウン", font=("Sans", 14), command=shutdown, width=24).pack(pady=10)
    root.deiconify(); root.attributes("-fullscreen", True); root.attributes("-topmost", True)
    root.lift(); root.focus_force()
    root.after(250, lambda: root.attributes("-fullscreen", True) if root.winfo_exists() else None)

def main():
    if not BASE or not TOKEN: raise SystemExit("PI_CONTROL_URL と PI_DEVICE_TOKEN を設定してください")
    threading.Thread(target=worker, daemon=True).start()
    root = tk.Tk(); root.title("Pi Family Control"); root.configure(bg="#101827")
    root.protocol("WM_DELETE_WINDOW", lambda: None); root.bind("<Alt-F4>", lambda event: "break"); root.bind("<Escape>", lambda event: "break"); root.withdraw()
    state = {"locked": False}
    def poll():
        try:
            with open(LOCK_FILE, encoding="utf-8") as stream: reason = json.load(stream).get("reason", "利用制限中")
            if not state["locked"] or not root.winfo_viewable(): show_locked(root, reason); state["locked"] = True
            else:
                for child in root.winfo_children():
                    if isinstance(child, tk.Frame):
                        labels = [item for item in child.winfo_children() if isinstance(item, tk.Label)]
                        if len(labels) > 1: labels[1].configure(text=reason)
        except (OSError, tk.TclError, ValueError):
            if state["locked"]: root.withdraw(); state["locked"] = False
        root.after(1000, poll)
    root.after(1000, poll); root.mainloop()

if __name__ == "__main__": main()
