"""Soft pink context card, drawn at the window's DPI without bitmap assets."""
from functools import lru_cache
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 252, 408
COMMANDS = (10, 11, 12, 13, 50, 20, 31, 32, 33, 40)
HITS = {10: (18, 72, 234, 102), 11: (18, 104, 234, 134),
        12: (18, 136, 234, 166), 13: (18, 168, 234, 198),
        50: (18, 224, 234, 256), 20: (18, 263, 234, 295),
        31: (18, 323, 86, 353), 32: (92, 323, 160, 353),
        33: (166, 323, 234, 353), 40: (18, 369, 234, 394)}


def hit_test(x, y):
    for command, (left, top, right, bottom) in HITS.items():
        if left <= x < right and top <= y < bottom:
            return command
    return None


@lru_cache(maxsize=16)
def font(size, bold=False):
    path = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / ('msyhbd.ttc' if bold else 'msyh.ttc')
    return ImageFont.truetype(str(path), size)


def render_menu(state, hover=None, dpi=1.0):
    # Supersampling keeps the rounded border and small icons smooth at 100%.
    factor = max(2, round(dpi*2))
    canvas = Image.new('RGBA', (WIDTH*factor, HEIGHT*factor))
    draw = ImageDraw.Draw(canvas)

    def box(rect):
        return tuple(round(v*factor) for v in rect)

    def rounded(rect, radius, fill, outline=None, width=1):
        draw.rounded_rectangle(box(rect), radius=round(radius*factor), fill=fill,
                               outline=outline, width=max(1, round(width*factor)))

    def line(points, fill, width=1.4):
        draw.line([tuple(round(v*factor) for v in point) for point in points],
                  fill=fill, width=max(1, round(width*factor)), joint='curve')

    def text(x, y, label, size=13, fill='#714b5d', bold=False, anchor=None):
        draw.text((round(x*factor), round(y*factor)), label, font=font(round(size*factor), bold),
                  fill=fill, anchor=anchor)

    shadow = Image.new('RGBA', canvas.size)
    ImageDraw.Draw(shadow).rounded_rectangle(box((10, 10, 242, 400)), radius=16*factor, fill=(106, 52, 76, 35))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(5*factor)))
    rounded((8, 6, 244, 398), 15, '#fff8fb', '#ecc5d5')
    # A quiet rose header with two small star accents.
    rounded((9, 7, 243, 63), 14, '#fce5ee')
    draw.rectangle(box((9, 47, 243, 64)), fill='#fce5ee')
    text(23, 16, '茜特菈莉', 16, '#824b65', True)
    text(24, 43, '陪你度过一点小日常', 9.5, '#ac7e92')

    def star(x, y, r, color):
        draw.polygon([box((x, y-r)), box((x+r*.28, y-r*.28)), box((x+r, y)),
                      box((x+r*.28, y+r*.28)), box((x, y+r)), box((x-r*.28, y+r*.28)),
                      box((x-r, y)), box((x-r*.28, y-r*.28))], fill=color)

    star(216, 28, 8, '#d58fab')
    star(230, 45, 3, '#e7b2c7')
    selected = 10 if state['auto'] else {'standing': 11, 'drinking': 12, 'reading': 13}[state['requested']]
    labels = {10: '自动轮换', 11: '站立待机', 12: '坐着喝饮料', 13: '趴着读书'}
    for command, label in labels.items():
        left, top, right, bottom = HITS[command]
        active = command == selected
        if active or command == hover:
            rounded((left, top, right, bottom), 9, '#f6d5e3' if active else '#fce8f0',
                    '#ecc0d1' if active else None)
        color = '#b2698b' if active else '#b591a2'
        cx, cy = left+17, top+15
        if command == 10:
            # Two offset arrows form the loop icon.
            line([(cx-6, cy-2), (cx-6, cy-6), (cx+6, cy-6), (cx+6, cy-2)], color)
            line([(cx+3, cy-5), (cx+6, cy-2), (cx+9, cy-5)], color)
            line([(cx+6, cy+2), (cx+6, cy+6), (cx-6, cy+6), (cx-6, cy+2)], color)
            line([(cx-9, cy+5), (cx-6, cy+2), (cx-3, cy+5)], color)
        elif command == 11:
            star(cx, cy, 7, color)
        elif command == 12:
            line([(cx-6, cy-4), (cx-4, cy+7), (cx+4, cy+7), (cx+6, cy-4), (cx-6, cy-4)], color)
            line([(cx, cy-4), (cx+2, cy-9), (cx+6, cy-9)], color)
        else:
            line([(cx, cy-5), (cx-7, cy-7), (cx-7, cy+5), (cx, cy+7), (cx+7, cy+5), (cx+7, cy-7), (cx, cy-5), (cx, cy+7)], color)
        text(left+35, top+6, label, 12, '#824b65' if active else '#806375', active)
        if active:
            line([(right-23, top+15), (right-20, top+18), (right-14, top+11)], '#b2698b', 1.7)
    pending = state.get('pending')
    text(23, 205, '结束后切换：'+labels[{'standing':11, 'drinking':12, 'reading':13}[pending]] if pending else '动作会自然衔接，慢慢陪着你',
         9.5, '#b18498')
    rounded(HITS[50], 10, '#f6d5e3' if hover == 50 else '#fff1f6', '#efcedc')
    draw.ellipse(box((27, 232, 43, 248)), outline='#b2698b', width=2*factor)
    draw.arc(box((30, 237, 40, 245)), 0, 180, fill='#b2698b', width=factor)
    for x in (32, 37):
        draw.ellipse(box((x, 236, x+1.3, 237.3)), fill='#b2698b')
    text(53, 231, '表情', 12, '#985d7b', True)
    text(216, 232, '9 款  ›', 10, '#b18498', anchor='rt')
    rounded(HITS[20], 10, '#f9e0eb' if hover == 20 else '#fcebf2', '#efcedc')
    text(126, 270, '▷  继续播放' if state['paused'] else 'Ⅱ  暂停动画', 11.5, '#985d7b', anchor='mt')
    text(20, 303, '显示大小', 10, '#ae8396')
    for command, label, scale in ((31, '小', .7), (32, '中', 1), (33, '大', 1.3)):
        active = abs(state['scale']-scale) < .01
        rounded(HITS[command], 9, '#f4d0e0' if active else '#fbe4ee' if hover == command else '#fffafd',
                '#e9b7cd' if active else '#eed5e0')
        left, top, right, bottom = HITS[command]
        text((left+right)/2, top+6, label, 11.5, '#9b607e' if active else '#a38293', active, 'mt')
    line([(20, 362), (232, 362)], '#eed6e1', .7)
    if hover == 40:
        rounded(HITS[40], 9, '#fbe4ed')
    text(126, 374, '退出桌宠', 11, '#ad8095', anchor='mt')
    return canvas.resize((round(WIDTH*dpi), round(HEIGHT*dpi)), Image.Resampling.LANCZOS)
