#!/usr/bin/env python3
import os,time,json,datetime,threading,tkinter as tk
from tkinter import messagebox,simpledialog
from urllib.request import Request,urlopen

BASE=os.environ.get("PI_CONTROL_URL","").rstrip("/")
TOKEN=os.environ.get("PI_DEVICE_TOKEN","")
DAYS=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
lock_file="/tmp/pi-family-control-lock.json"
def api(path,method="GET",payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=Request(BASE+path,data=data,method=method,headers={"X-Device-Token":TOKEN,"Content-Type":"application/json"})
    with urlopen(req,timeout=8) as r:return json.loads(r.read().decode())
def now():return datetime.datetime.now().astimezone()
def datekey(dt):return dt.strftime("%Y-%m-%d")
def in_time(dt,start,end):
    sh,sm=map(int,start.split(":"));eh,em=map(int,end.split(":"));n=dt.hour*60+dt.minute;a=sh*60+sm;b=eh*60+em
    if a==b:return True
    return a<=n<b if a<b else n>=a or n<b
def allowed(c,dt):
    ctl=c.get("control",{});s=c.get("settings",{})
    if ctl.get("manualLock"):return False,"管理サイトから手動ロックされています"
    if s.get("scheduleEnabled"):
        d=c.get("schedule",{}).get(DAYS[dt.weekday()],{})
        if not d.get("enabled") or not in_time(dt,d.get("start","00:00"),d.get("end","00:00")):return False,"利用できる時間帯の外です"
    limit=s.get("dailyLimitMinutes")
    if limit is not None:
        used=int((c.get("usage",{}).get("daily",{}).get(datekey(dt)) or {}).get("seconds",0))
        extra=int(ctl.get("todayExtensionMinutes",0)) if ctl.get("extensionDate")==datekey(dt) else 0
        if used >= (int(limit)+extra)*60:return False,"今日の使用上限に達しました"
    return True,"利用できます"
def report(sec):
    if sec<=0:return
    try:api("/api/device-report","POST",{"date":datekey(now()),"seconds":min(120,int(sec))})
    except Exception as e:print("usage report:",e,flush=True)
def worker():
    total=0;last=time.monotonic();lastreport=last
    while True:
        t=time.monotonic();delta=max(0,min(20,t-last));last=t
        try:c=api("/api/device-state")
        except Exception as e:
            print("cloud error:",e,flush=True);c={"settings":{"scheduleEnabled":True,"dailyLimitMinutes":1},"control":{"manualLock":True}}
        dt=now();ok,reason=allowed(c,dt)
        if ok:total+=delta
        if t-lastreport>=60:report(total);total=0;lastreport=t
        try:
            if ok:
                if os.path.exists(lock_file):os.remove(lock_file)
            else:
                with open(lock_file,"w") as f:json.dump({"reason":reason},f)
        except OSError:pass
        time.sleep(10)
def shutdown():
    if messagebox.askyesno("確認","ラズパイをシャットダウンしますか？"):os.system("systemctl poweroff")
def locked_screen(root,reason):
    win=tk.Toplevel(root);win.attributes("-fullscreen",True);win.attributes("-topmost",True);win.configure(bg="#101827");win.protocol("WM_DELETE_WINDOW",lambda:None);win.bind("<Alt-F4>",lambda e:"break");win.bind("<Escape>",lambda e:"break")
    frame=tk.Frame(win,bg="#101827");frame.place(relx=.5,rely=.5,anchor="center")
    tk.Label(frame,text="利用できません",font=("Sans",30,"bold"),fg="white",bg="#101827").pack(pady=12)
    tk.Label(frame,text=reason,font=("Sans",15),fg="white",bg="#101827",wraplength=650).pack(pady=10)
    tk.Label(frame,text="管理サイトからロック解除・延長してください",font=("Sans",12),fg="#ccd5e2",bg="#101827").pack(pady=8)
    tk.Button(frame,text="シャットダウン",font=("Sans",14),command=shutdown,width=24).pack(pady=10)
    return win
def main():
    if not BASE or not TOKEN:raise SystemExit("PI_CONTROL_URL と PI_DEVICE_TOKEN を設定してください")
    threading.Thread(target=worker,daemon=True).start()
    root=tk.Tk();root.withdraw();state={"window":None}
    def poll():
        try:
            with open(lock_file) as f:reason=json.load(f).get("reason","利用制限中")
            if not state["window"] or not state["window"].winfo_exists():state["window"]=locked_screen(root,reason)
        except (OSError,tk.TclError,ValueError):
            if state["window"]:
                try:state["window"].destroy()
                except tk.TclError:pass
                state["window"]=None
        root.after(1000,poll)
    root.after(1000,poll);root.mainloop()
if __name__=="__main__":main()
