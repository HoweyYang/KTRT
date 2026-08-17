# -*- coding: utf-8 -*-
"""KTRT 启动预备弹窗：带球小人 + 绿色渐变进度条（终点为球门）。"""
import os
import socket
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

TOTAL_TICKS = 100
TICK_MS = 30  # 约 3 秒
READY_TIMEOUT = 20


def _pick_font(root, size):
    fams = set(tkfont.families(root))
    for f in ('Ravie', 'Ink Free', 'Segoe UI Black', 'Impact', 'Arial Black'):
        if f in fams:
            return (f, size)
    return ('Segoe UI', size)


def _port_open(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_splash(host, port, asset_dir):
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    W, H = 480, 338
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry('%dx%d+%d+%d' % (W, H, (sw - W) // 2, (sh - H) // 2))
    root.configure(bg='#ffffff')

    state = {'done': False, 'ready': False}

    title_font = _pick_font(root, 20)
    tk.Label(root, text='KillTimeRecitationTool', font=title_font, fg='#17202a', bg='#ffffff').pack(pady=(16, 0))
    tk.Label(root, text='by HoweyYueng', font=('Segoe UI', 10, 'italic'), fg='#7f8c9b', bg='#ffffff').pack(pady=(0, 4))

    img_path = os.path.join(asset_dir, 'dribble.png')
    if os.path.exists(img_path):
        photo = tk.PhotoImage(file=img_path)
        tk.Label(root, image=photo, bg='#ffffff').pack(pady=(2, 0))
        root.photo = photo
    else:
        tk.Label(root, text='⚽', font=('Segoe UI', 40), bg='#ffffff').pack(pady=(4, 0))

    canvas = tk.Canvas(root, width=W - 40, height=70, bg='#ffffff', highlightthickness=0)
    canvas.pack(pady=(4, 0))

    y0 = 24
    x0 = 18
    x1 = W - 40 - 88
    # 进度槽
    canvas.create_rectangle(x0, y0 - 3, x1, y0 + 11, fill='#e8edf2', outline='')
    # 球门（右端终点）
    gx = x1 + 18
    gy0 = y0 - 16
    gy1 = y0 + 16
    canvas.create_rectangle(gx, gy0, gx + 18, gy1, outline='#17202a', width=2)
    canvas.create_line(gx, gy0, gx + 18, gy0, fill='#17202a', width=2)
    for i in range(1, 4):
        canvas.create_line(gx, gy0 + i * 7, gx + 18, gy0 + i * 7, fill='#c3ccd6')
    for j in range(1, 3):
        canvas.create_line(gx + j * 5, gy0, gx + j * 5, gy1, fill='#c3ccd6')

    bar = canvas.create_rectangle(x0, y0 - 3, x0, y0 + 11, fill='#7cfc00', outline='')
    status = tk.Label(root, text='正在准备词库…', font=('Microsoft YaHei UI', 9), fg='#5d6b7e', bg='#ffffff')
    status.pack(pady=(0, 10))

    def close(ready):
        state['ready'] = ready
        state['done'] = True
        try:
            root.destroy()
        except Exception:
            pass

    def waiter():
        deadline = time.time() + READY_TIMEOUT
        while time.time() < deadline and not state['done']:
            if _port_open(host, port):
                try:
                    root.after(0, lambda: close(True))
                except Exception:
                    pass
                return
            time.sleep(0.2)
        if not state['done']:
            try:
                root.after(0, lambda: close(False))
            except Exception:
                pass

    def animate(i=0):
        if state['done']:
            return
        p = min(1.0, i / TOTAL_TICKS)
        xw = x0 + (x1 - x0) * p
        canvas.coords(bar, x0, y0 - 3, xw, y0 + 11)
        r = int(0x7C + (0x00 - 0x7C) * p)
        g = int(0xFC + (0x64 - 0xFC) * p)
        b = 0
        canvas.itemconfig(bar, fill='#%02x%02x%02x' % (r, g, b))
        status.config(text='正在准备词库… %d%%' % int(p * 100))
        if i < TOTAL_TICKS:
            root.after(TICK_MS, lambda: animate(i + 1))
        else:
            status.config(text='等待服务就绪…')
            root.after(200, lambda: animate(i))

    threading.Thread(target=waiter, daemon=True).start()
    animate()
    root.mainloop()
    return state['ready']
