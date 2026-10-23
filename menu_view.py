"""Soft pink context card, drawn at the window's DPI without bitmap assets."""
from functools import lru_cache
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 140, 240
COMMANDS = (10, 11, 12, 13, 14, 50, 60, 20, 31, 32, 33, 40)
HITS = {10: (9, 31, 131, 50), 11: (9, 51, 131, 70),
        12: (9, 71, 131, 90), 13: (9, 91, 131, 110),
        14: (9, 111, 131, 130),
        50: (9, 135, 68, 156), 60: (72, 135, 131, 156), 20: (9, 160, 131, 181),
        31: (9, 187, 47, 208), 32: (51, 187, 89, 208),
        33: (93, 187, 131, 208), 40: (9, 215, 131, 234)}


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
    ImageDraw.Draw(shadow).rounded_rectangle(box((6, 6, 134, 236)), radius=11*factor, fill=(106, 52, 76, 35))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3*factor)))
    rounded((4, 3, 136, 236), 10, '#fff8fb', '#ecc5d5')
    # A quiet rose header with two small star accents.
    rounded((5, 4, 135, 27), 9, '#fce5ee')
    draw.rectangle(box((5, 17, 135, 28)), fill='#fce5ee')
    text(14, 8, '茜特菈莉', 11.5, '#824b65', True)

    def star(x, y, r, color):
        draw.polygon([box((x, y-r)), box((x+r*.28, y-r*.28)), box((x+r, y)),
                      box((x+r*.28, y+r*.28)), box((x, y+r)), box((x-r*.28, y+r*.28)),
                      box((x-r, y)), box((x-r*.28, y-r*.28))], fill=color)

    star(119, 16, 5, '#d58fab')
    selected = 14 if state.get('walking') else 10 if state['auto'] else {'standing': 11, 'drinking': 12, 'reading': 13}[state['requested']]
    labels = {10: '自动轮换', 11: '站立待机', 12: '坐着喝饮料', 13: '趴着读书', 14: '自由走动'}
    for command, label in labels.items():
        left, top, right, bottom = HITS[command]
        active = command == selected
        if active or command == hover:
            rounded((left, top, right, bottom), 5, '#f6d5e3' if active else '#fce8f0',
                    '#ecc0d1' if active else None)
        color = '#b2698b' if active else '#b591a2'
        cx, cy = left+10, top+9.5
        if command == 10:
            # Two offset arrows form the loop icon.
            line([(cx-4, cy-1), (cx-4, cy-4), (cx+4, cy-4), (cx+4, cy-1)], color, 1)
            line([(cx+2, cy-3), (cx+4, cy-1), (cx+6, cy-3)], color, 1)
            line([(cx+4, cy+1), (cx+4, cy+4), (cx-4, cy+4), (cx-4, cy+1)], color, 1)
            line([(cx-6, cy+3), (cx-4, cy+1), (cx-2, cy+3)], color, 1)
        elif command == 11:
            star(cx, cy, 5, color)
        elif command == 12:
            line([(cx-4, cy-3), (cx-3, cy+5), (cx+3, cy+5), (cx+4, cy-3), (cx-4, cy-3)], color, 1)
            line([(cx, cy-3), (cx+1, cy-6), (cx+4, cy-6)], color, 1)
        elif command == 14:
            line([(cx-5,cy+4),(cx-1,cy-1),(cx+2,cy+1),(cx+5,cy-4)],color,1.2)
            line([(cx+1,cy-4),(cx+5,cy-4),(cx+5,cy)],color,1.2)
        else:
            line([(cx, cy-3), (cx-5, cy-4), (cx-5, cy+3), (cx, cy+5), (cx+5, cy+3), (cx+5, cy-4), (cx, cy-3), (cx, cy+5)], color, 1)
        text(left+22, top+3, label, 9.5, '#824b65' if active else '#806375', active)
        if active:
            if state.get('pending') and command != 10:
                text(right-6, top+4, '待切换', 7.5, '#b2698b', anchor='rt')
            else:
                line([(right-14, top+9), (right-12, top+11), (right-8, top+6)], '#b2698b', 1.2)
    rounded(HITS[50], 6, '#f6d5e3' if hover == 50 else '#fff1f6', '#efcedc')
    draw.ellipse(box((14, 140, 25, 151)), outline='#b2698b', width=factor)
    draw.arc(box((16, 143, 23, 149)), 0, 180, fill='#b2698b', width=factor)
    for x in (17, 21):
        draw.ellipse(box((x, 143, x+1, 144)), fill='#b2698b')
    text(31, 139, '表情', 9.5, '#985d7b', True)
    rounded(HITS[60], 6, '#f6d5e3' if hover == 60 else '#fff1f6', '#efcedc')
    draw.polygon([box((78, 143)), box((81, 143)), box((85, 140)),
                  box((85, 151)), box((81, 148)), box((78, 148))], fill='#b2698b')
    draw.arc(box((83, 140, 90, 152)), -70, 70, fill='#b2698b', width=factor)
    text(96, 139, '语音', 9.5, '#985d7b', True)
    rounded(HITS[20], 6, '#f9e0eb' if hover == 20 else '#fcebf2', '#efcedc')
    text(70, 164, '▷  继续播放' if state['paused'] else 'Ⅱ  暂停动画', 9.5, '#985d7b', anchor='mt')
    for command, label, scale in ((31, '小', .7), (32, '中', 1), (33, '大', 1.3)):
        active = abs(state['scale']-scale) < .01
        rounded(HITS[command], 5, '#f4d0e0' if active else '#fbe4ee' if hover == command else '#fffafd',
                '#e9b7cd' if active else '#eed5e0')
        left, top, right, bottom = HITS[command]
        text((left+right)/2, top+4, label, 9.5, '#9b607e' if active else '#a38293', active, 'mt')
    line([(12, 212), (128, 212)], '#eed6e1', .7)
    if hover == 40:
        rounded(HITS[40], 5, '#fbe4ed')
    text(70, 218, '退出桌宠', 9, '#ad8095', anchor='mt')
    return canvas.resize((round(WIDTH*dpi), round(HEIGHT*dpi)), Image.Resampling.LANCZOS)
