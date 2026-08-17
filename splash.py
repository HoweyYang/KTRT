# -*- coding: utf-8 -*-
"""KTRT 启动预备弹窗 v4：透明抠图小人从左往右踢向球门 + 绿色渐变进度条。

- 带球小人（透明抠图）整体从左往右移动，人和球都在图里；
- 进度条随小人同步从左往右填充，绿色渐变加深，终点是球门；
- 空白区域用抽象字体写 KTRT 全名，副标为宣传语 + by HoweyYueng；
- 动画固定约 3 秒（服务秒就绪也要播完 3 秒）；
- 服务探测在主线程完成（避免跨线程 after 不生效导致弹窗不关闭）。
"""
import os
import socket
import time
import tkinter as tk
import tkinter.font as tkfont

TOTAL_TICKS = 100
TICK_MS = 30            # 100 * 30ms = 3 秒
READY_TIMEOUT = 25      # 动画播完后最多再等服务 25 秒


def _pick_font(root, size):
    fams = set(tkfont.families(root))
    for f in ('Ravie', 'Ink Free', 'Segoe UI Black', 'Impact', 'Arial Black'):
        if f in fams:
            return (f, size)
    return ('Segoe UI', size)


def _port_open(host, port, timeout=0.3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_splash(host, port, asset_dir):
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    W, H = 560, 380
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry('%dx%d+%d+%d' % (W, H, (sw - W) // 2, (sh - H) // 2))
    root.configure(bg='#ffffff')

    state = {'done': False, 'ready': False}
    t_start = time.time()

    # 标题（抽象字体）+ 宣传语 + 副标
    tk.Label(root, text='KillTimeRecitationTool', font=_pick_font(root, 22),
             fg='#17202a', bg='#ffffff').pack(pady=(16, 0))
    tk.Label(root, text='更加人性化及知识更齐全的本地CRUSH VOCAB软件',
             font=('Microsoft YaHei UI', 10), fg='#4a5a6e', bg='#ffffff').pack(pady=(3, 0))
    tk.Label(root, text='by HoweyYueng', font=('Segoe UI', 9, 'italic'),
             fg='#7f8c9b', bg='#ffffff').pack(pady=(2, 4))

    # 动画画布
    canvas = tk.Canvas(root, width=W - 24, height=178, bg='#ffffff', highlightthickness=0)
    canvas.pack()

    canvas_width = W - 24
    y_track = 148            # 轨道（小人贴地行走的线）
    x0 = 56                  # 左侧起点
    goal_w = 34              # 球门宽度
    goal_h = 50              # 球门高度
    right_margin = 14
    gx = canvas_width - right_margin - goal_w   # 球门左立柱，进度条终点直接连到它
    gy0 = y_track - 32
    gy1 = y_track + 14
    # 轨道槽：从起点一路连到球门左立柱，不留缺口
    canvas.create_rectangle(x0, y_track - 5, gx, y_track + 7, fill='#e8edf2', outline='')
    # 球门（终点），左立柱与轨道槽相接
    canvas.create_rectangle(gx, gy0, gx + goal_w, gy1, outline='#17202a', width=2)
    canvas.create_line(gx, gy0, gx + goal_w, gy0, fill='#17202a', width=2)
    for i in range(1, 4):
        canvas.create_line(gx, gy0 + i * 12, gx + goal_w, gy0 + i * 12, fill='#c3ccd6')
    for j in range(1, 3):
        canvas.create_line(gx + j * 11, gy0, gx + j * 11, gy1, fill='#c3ccd6')

    # 绿色渐变进度条（从左往右填充，终点连到球门左立柱）
    bar = canvas.create_rectangle(x0, y_track - 5, x0, y_track + 7, fill='#7cfc00', outline='')

    # 带球小人（透明抠图，整张图从左往右移动）
    img_item = None
    img_path = os.path.join(asset_dir, 'assets', 'dribble_small.png')
    if os.path.exists(img_path):
        photo = tk.PhotoImage(file=img_path)
        root.photo = photo
        img_item = canvas.create_image(x0, y_track + 2, anchor='s', image=photo)
    else:
        img_item = canvas.create_text(x0, y_track - 4, text='⚽', font=('Segoe UI', 30), anchor='s')

    status = tk.Label(root, text='正在准备词库…', font=('Microsoft YaHei UI', 9),
                      fg='#5d6b7e', bg='#ffffff')
    status.pack(pady=(0, 12))

    def close(ready):
        state['ready'] = ready
        state['done'] = True
        try:
            root.photo = None  # 在 Tcl 解释器销毁前释放图片，避免 Image.__del__ 报错
            root.destroy()
        except Exception:
            pass

    def animate(i=0):
        if state['done']:
            return
        p = min(1.0, i / TOTAL_TICKS)
        xw = x0 + (gx - x0) * p
        canvas.coords(bar, x0, y_track - 5, xw, y_track + 7)
        r = int(0x7C + (0x00 - 0x7C) * p)
        g = int(0xFC + (0x64 - 0xFC) * p)
        b = 0
        canvas.itemconfig(bar, fill='#%02x%02x%02x' % (r, g, b))
        px = x0 + (gx - x0) * p
        if img_item is not None:
            canvas.coords(img_item, px, y_track + 2)
        status.config(text='正在准备词库… %d%%' % int(p * 100))
        if i < TOTAL_TICKS:
            root.after(TICK_MS, lambda: animate(i + 1))
        else:
            # 动画播完：主线程轮询服务端口，就绪即关；最多等到 READY_TIMEOUT
            if _port_open(host, port):
                close(True)
            elif time.time() - t_start > READY_TIMEOUT:
                close(False)
            else:
                status.config(text='等待服务就绪…')
                root.after(300, lambda: animate(i))

    animate()
    root.mainloop()
    return state['ready']




