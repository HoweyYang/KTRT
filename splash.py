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
SPLASH_WIDTH = 720
SPLASH_HEIGHT = 500
SPLASH_PALETTE = {
    'background': '#101b25',
    'ink': '#f3eee6',
    'muted': '#b9c3bc',
    'subtle': '#99a7aa',
    'field': '#315b43',
    'field_edge': '#547561',
    'field_line': '#d3e5d2',
    'goal': '#d5e4d5',
    'accent': '#20ad70',
}
DESCRIPTOR_FONT = ('Segoe UI', 10, 'italic')
# 签名用系统里的手写花体：Edwardian Script 最接近 Apple 那种优雅手写，后面几个做兜底
SIGNATURE_FONTS = ('Edwardian Script ITC', 'Kunstler Script', 'Monotype Corsiva',
                   'Segoe Script', 'Ink Free')
SIGNATURE_TEXT = 'Designed by HoweyYueng'
# 中文主标题：思源宋体优先（比雅黑更有书卷气），没有就退到华文中宋、雅黑
TITLE_FONTS = ('Noto Serif SC SemiBold', 'Noto Serif SC', 'STZhongsong', 'Microsoft YaHei UI')
SUBTITLE_FONTS = ('Noto Serif SC', 'Noto Serif SC Light', 'STZhongsong', 'Microsoft YaHei UI')


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


def _pick_family(root, candidates, fallback='Segoe UI'):
    """挑第一个系统里真装了的字体，避免静默落到 Tk 默认字体。"""
    fams = set(tkfont.families(root))
    for name in candidates:
        if name in fams:
            return name
    return fallback


def run_splash(host, port, asset_dir):
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    W, H = SPLASH_WIDTH, SPLASH_HEIGHT
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry('%dx%d+%d+%d' % (W, H, (sw - W) // 2, (sh - H) // 2))
    palette = SPLASH_PALETTE
    root.configure(bg=palette['background'])

    state = {'done': False, 'ready': False}
    t_start = time.time()

    # 品牌区：主标题更大，英文副标保留原来的 Segoe UI 斜体。
    top = tk.Frame(root, bg=palette['background'])
    top.pack(fill='x', padx=42, pady=(25, 0))
    tk.Label(top, text='KTRT', font=('Segoe UI', 10, 'bold'),
             fg=palette['muted'], bg=palette['background']).pack(side='left')
    tk.Label(top, text='LOCAL APP', font=('Segoe UI', 10),
             fg=palette['subtle'], bg=palette['background']).pack(side='right')
    tk.Label(root, text='溯源词斩', font=(_pick_family(root, TITLE_FONTS), 32),
             fg=palette['ink'], bg=palette['background']).pack(anchor='w', padx=48, pady=(14, 0))
    tk.Label(root, text='本地优先的单词学习工具', font=(_pick_family(root, SUBTITLE_FONTS), 15),
             fg=palette['muted'], bg=palette['background']).pack(anchor='w', padx=48, pady=(3, 0))
    # 签名区：上面一行是 KTRT 全称（镶金），下面一行是手写花体签名。
    # 流光用「整串文字 + 按字符区间上亮色」实现：花体的连笔不会被拆开，
    # 亮色区间从左往右走，就是光扫过去的感觉 —— 不做发光副本，所以不糊。
    script_font = (_pick_family(root, SIGNATURE_FONTS, 'Segoe Script'), 23)
    sign_zone = tk.Frame(root, bg=palette['background'])
    sign_zone.pack(anchor='w', padx=48, pady=(4, 0))

    def _shimmer_line(parent, text, font, base_color, bright_color):
        f = tkfont.Font(font=font)
        chars = int(f.measure(text) / max(1, f.measure('0'))) + 2
        widget = tk.Text(parent, height=1, width=chars, font=font, bd=0, relief='flat',
                         highlightthickness=0, padx=0, pady=0, cursor='arrow',
                         bg=palette['background'], fg=base_color)
        widget.insert('1.0', text)
        widget.tag_configure('bright', foreground=bright_color)
        widget.configure(state='disabled')
        return widget

    GOLD_TEXT = 'KILLTIME RECITATION TOOL'
    gold_line = _shimmer_line(sign_zone, GOLD_TEXT, DESCRIPTOR_FONT, '#9c7c34', '#ffeaa8')
    gold_line.pack(anchor='w')
    sig_line = _shimmer_line(sign_zone, SIGNATURE_TEXT, script_font, '#67808f', '#ffffff')
    sig_line.pack(anchor='w', pady=(3, 0))
    sweep = {'i': -8}

    def animate_sweep():
        if state['done']:
            return
        for widget, text in ((gold_line, GOLD_TEXT), (sig_line, SIGNATURE_TEXT)):
            total = len(text)
            widget.tag_remove('bright', '1.0', 'end')
            start, end = max(0, sweep['i'] - 8), min(total, sweep['i'])
            if end > start:
                widget.tag_add('bright', '1.%d' % start, '1.%d' % end)
        sweep['i'] += 1
        if sweep['i'] > max(len(GOLD_TEXT), len(SIGNATURE_TEXT)) + 8:
            sweep['i'] = -8
        root.after(110, animate_sweep)

    animate_sweep()

    # 球场本身就是进度条：草纹、场线和从左向右的绿色渐变共用一块画布。
    canvas = tk.Canvas(root, width=W - 84, height=226, bg=palette['background'], highlightthickness=0)
    canvas.pack(pady=(15, 0))
    canvas_width = W - 84
    field_x = 22
    field_top = 88
    field_w = canvas_width - 44
    field_h = 64
    field_bottom = field_top + field_h
    field_right = field_x + field_w
    player_y = field_top + field_h // 2 + 12

    canvas.create_rectangle(field_x, field_top, field_right, field_bottom,
                             fill=palette['field'], outline=palette['field_edge'], width=2)
    # 草干：低对比斜纹，不抢人物和进度的视觉焦点。
    for x in range(field_x + 8, field_right, 13):
        canvas.create_line(x, field_top + 7, x - 5, field_bottom - 7,
                           fill='#6f9b79', width=1)
    segments = 48
    seg_w = field_w / segments
    progress_items = []
    for i in range(segments):
        progress_items.append(canvas.create_rectangle(
            field_x + i * seg_w, field_top + 1,
            field_x + (i + 1) * seg_w + .5, field_bottom - 1,
            fill=palette['field'], outline=''))
    # 再压一层草干，让未完成与已完成区域都保留足球场质感。
    for x in range(field_x + 8, field_right, 13):
        canvas.create_line(x, field_top + 7, x - 5, field_bottom - 7,
                           fill='#6f9b79', width=1)
    # 俯拍球场线：中线、圆和内框均压在进度层之上。
    canvas.create_rectangle(field_x + 7, field_top + 7, field_right - 7, field_bottom - 7,
                             outline=palette['field_line'], width=1)
    mid_x = field_x + field_w / 2
    canvas.create_line(mid_x, field_top + 7, mid_x, field_bottom - 7,
                       fill=palette['field_line'], width=1)
    canvas.create_oval(mid_x - 15, field_top + field_h / 2 - 15,
                       mid_x + 15, field_top + field_h / 2 + 15,
                       outline=palette['field_line'], width=1)
    canvas.create_oval(mid_x - 2, field_top + field_h / 2 - 2,
                       mid_x + 2, field_top + field_h / 2 + 2,
                       fill=palette['field_line'], outline='')

    # 俯拍球门：窄门线 + 向右伸出的梯形网面，和球场中线对齐。
    # 球门与徽标整体往左收，让它们完整落在画布内：
    # 画布会硬裁超出部分，之前球门网右缘到 519、徽标右缘到 537（画布只有 516），
    # 所以 GOAL! 右边被切掉。现在球门右缘与球场右端齐平，徽标居中在其上方。
    goal_x = field_right - 26
    net_top = field_top + 14
    net_bottom = field_bottom - 14
    goal_items = []
    goal_items.append(canvas.create_line(goal_x, net_top, goal_x, net_bottom,
                                         fill=palette['goal'], width=2, state='hidden'))
    goal_items.append(canvas.create_polygon(
        goal_x, net_top, goal_x + 27, net_top + 3,
        goal_x + 27, net_bottom - 3, goal_x, net_bottom,
        outline=palette['goal'], fill='', width=1, state='hidden'))
    for i in range(1, 4):
        goal_items.append(canvas.create_line(
            goal_x + i * 7, net_top + 3, goal_x + i * 7,
            net_bottom - 3, fill='#8da998', width=1, state='hidden'))
    for i in range(1, 3):
        goal_items.append(canvas.create_line(
            goal_x + 1, net_top + i * 8, goal_x + 26,
            net_top + i * 8 + 2, fill='#8da998', width=1, state='hidden'))
    badge_x = goal_x + 14
    badge_y = field_top - 13
    badge_box = canvas.create_rectangle(badge_x - 27, badge_y - 10, badge_x + 27, badge_y + 10,
                                        fill=palette['accent'], outline='', state='hidden')
    badge_text = canvas.create_text(badge_x, badge_y, text='GOAL!',
                                    font=('Segoe UI', 10, 'bold'), fill='#ffffff', state='hidden')
    goal_items.extend([badge_box, badge_text])

    # 拖影分两层，和设计稿一致：两张去色残影（跟在身后）＋三条速度线。
    # 小人本体只加载这一次，残影是用去色降透明预处理好的副本。
    ghost_items = []
    for idx, ghost_name in enumerate(('dribble_ghost_1.png', 'dribble_ghost_2.png')):
        ghost_path = os.path.join(asset_dir, 'assets', ghost_name)
        if not os.path.exists(ghost_path):
            continue
        ghost_photo = tk.PhotoImage(file=ghost_path)
        setattr(root, 'ghost_photo_%d' % idx, ghost_photo)   # 挂在 root 上，否则会被回收
        ghost_items.append(canvas.create_image(-200, player_y, anchor='s',
                                              image=ghost_photo, state='hidden'))
    trail_lines = [
        canvas.create_line(0, 0, 0, 0, fill='#8db89a', width=2, state='hidden'),
        canvas.create_line(0, 0, 0, 0, fill='#6d9d7d', width=1, state='hidden'),
        canvas.create_line(0, 0, 0, 0, fill='#9fc4aa', width=1, state='hidden'),
    ]
    img_item = None
    img_path = os.path.join(asset_dir, 'assets', 'dribble_small.png')
    if os.path.exists(img_path):
        photo = tk.PhotoImage(file=img_path)
        root.photo = photo
        img_item = canvas.create_image(field_x + 14, player_y, anchor='s', image=photo)
    else:
        img_item = canvas.create_text(field_x + 14, player_y - 4, text='⚽',
                                      font=('Segoe UI', 30), anchor='s', fill=palette['ink'])

    status = tk.Label(root, text='正在准备词库…', font=('Microsoft YaHei UI', 11),
                      fg=palette['muted'], bg=palette['background'])
    status.pack(anchor='w', padx=42, pady=(0, 16))
    goal_shown = {'value': False}
    close_scheduled = {'value': False}

    def _gradient_color(p):
        start = (0xb7, 0xec, 0x55)
        end = (0x16, 0xa9, 0x65)
        return '#%02x%02x%02x' % tuple(int(a + (b - a) * p) for a, b in zip(start, end))

    def show_goal():
        if goal_shown['value']:
            return
        goal_shown['value'] = True
        for item in goal_items:
            canvas.itemconfigure(item, state='normal')
        # 徽标建在人物之前，不抬到最上层会被人物挡住（设计稿里它是压在人物肩上的）
        canvas.tag_raise(badge_box)
        canvas.tag_raise(badge_text)
        pulse_goal(0)

    def pulse_goal(step):
        if state['done']:
            return
        scale = .72 + min(step, 6) / 6 * .28
        half_w, half_h = 27 * scale, 10 * scale
        canvas.coords(badge_box, badge_x - half_w, badge_y - half_h,
                      badge_x + half_w, badge_y + half_h)
        canvas.coords(badge_text, badge_x, badge_y)
        if step < 6:
            root.after(45, lambda: pulse_goal(step + 1))

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
        active = int(p * segments)
        for j, item in enumerate(progress_items):
            fill_p = j / max(1, segments - 1)
            canvas.itemconfig(item, fill=_gradient_color(fill_p) if j < active else palette['field'])
        px = field_x + (field_w - 28) * p
        if img_item is not None:
            canvas.coords(img_item, px, player_y)
        for idx, line in enumerate(trail_lines):
            if .04 < p < .98:
                offset = 34 + idx * 11
                y = player_y - 22 + idx * 10
                canvas.coords(line, px - offset - 26, y, px - offset, y - 2)
                canvas.itemconfigure(line, state='normal')
            else:
                canvas.itemconfigure(line, state='hidden')
        for idx, item in enumerate(ghost_items):
            if .12 < p < .96:
                canvas.coords(item, px - 17 - idx * 15, player_y - idx)
                canvas.itemconfigure(item, state='normal')
            else:
                canvas.itemconfigure(item, state='hidden')
        if p < 1:
            status.config(text='正在准备词库… %d%%' % int(p * 100))
        if i < TOTAL_TICKS:
            root.after(TICK_MS, lambda: animate(i + 1))
        else:
            show_goal()
            # 动画播完：主线程轮询服务端口，就绪即关；最多等到 READY_TIMEOUT
            if _port_open(host, port):
                status.config(text='准备完成，正在打开 KTRT…')
                if not close_scheduled['value']:
                    close_scheduled['value'] = True
                    root.after(520, lambda: close(True))
            elif time.time() - t_start > READY_TIMEOUT:
                close(False)
            else:
                status.config(text='等待本地服务就绪…')
                root.after(300, lambda: animate(i))

    animate()
    root.mainloop()
    return state['ready']

def main():
    """独立进程入口：pythonw splash.py --host 127.0.0.1 --port 8000 --assets DIR"""
    import argparse
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--assets', default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    ok = run_splash(args.host, args.port, args.assets)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
