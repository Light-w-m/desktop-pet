"""Small transparent stickers, a pink picker and a passive companion window."""
import ctypes as C
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .menu_view import font
from .pet_menu import PinkMenu, monitor_work_area, rgba_pixels

EXPRESSIONS = (('panic', '慌张'), ('sleep', '睡了'), ('suspicious', '怀疑'),
               ('hide', '不想面对'), ('wake', '刚醒'), ('blush', '脸红'),
               ('annoyed', '有点烦'), ('hello', '来了'), ('wink', '眨眼'))
HIDDEN_EXPRESSIONS = {'shake_angry': 'shake-angry.png'}
PICKER_WIDTH, PICKER_HEIGHT = 176, 244
PICKER_HITS = {51: (10, 9, 48, 29), 52: (133, 9, 166, 29)}
PICKER_HITS.update({101+i: (10+54*(i % 3), 38+62*(i//3),
                          58+54*(i % 3), 96+62*(i//3)) for i in range(9)})


class StickerLibrary:
    def __init__(self, folder, fallback):
        self.folder, self.fallback = folder, fallback

    def path(self, key):
        if key in HIDDEN_EXPRESSIONS:
            filename = HIDDEN_EXPRESSIONS[key]
            path = self.folder.parent/'easter-eggs'/filename
            if not path.is_file():
                path = self.fallback.parent/'easter-eggs'/filename
            if not path.is_file():
                raise FileNotFoundError('Missing hidden expression: '+key)
            return path
        if key not in dict(EXPRESSIONS):
            raise ValueError('Unknown expression: '+key)
        path = self.folder/(key+'.png')
        if not path.is_file():
            path = self.fallback/(key+'.png')
        if not path.is_file():
            raise FileNotFoundError('Missing expression: '+key)
        return path

    @lru_cache(maxsize=18)
    def image(self, key, size):
        with Image.open(self.path(key)) as source:
            rgba = source.convert('RGBA')
        bounds = rgba.getbbox()
        if bounds is None:
            raise ValueError('Empty expression: '+key)
        # Decode only requested thumbnails; never retain all full-size sources.
        return ImageOps.contain(rgba.crop(bounds), (size, size), Image.Resampling.LANCZOS)


def render_picker(library, state, hover=None, dpi=1):
    factor = max(2, round(2*dpi))
    canvas = Image.new('RGBA', (PICKER_WIDTH*factor, PICKER_HEIGHT*factor))
    draw = ImageDraw.Draw(canvas)

    def box(rect):
        return tuple(round(x*factor) for x in rect)

    def rounded(rect, radius, fill, outline=None, width=1):
        draw.rounded_rectangle(box(rect), radius=round(radius*factor), fill=fill,
                               outline=outline, width=round(width*factor))

    def text(x, y, label, size=12, fill='#985d7b', bold=False, anchor=None):
        draw.text((round(x*factor), round(y*factor)), label,
                  font=font(round(size*factor), bold), fill=fill, anchor=anchor)

    shadow = Image.new('RGBA', canvas.size)
    ImageDraw.Draw(shadow).rounded_rectangle(box((6, 6, 170, 240)), radius=11*factor,
                                             fill=(106, 52, 76, 35))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3*factor)))
    rounded((4, 3, 172, 240), 10, '#fff8fb', '#ecc5d5')
    rounded((5, 4, 171, 30), 9, '#fce5ee')
    draw.rectangle(box((5, 20, 171, 31)), fill='#fce5ee')
    if hover == 51:
        rounded(PICKER_HITS[51], 5, '#f3cfdf')
    text(14, 12, '‹ 返回', 8.5)
    text(58, 10, '今天的心情', 10, '#824b65', True)
    selected = state['expression']
    rounded(PICKER_HITS[52], 5, '#f3cfdf' if hover == 52 else '#fff5f9', '#eac3d4')
    text(149, 12, '清除', 8.5, '#985d7b' if selected else '#b597a6', anchor='mt')
    for i, (key, label) in enumerate(EXPRESSIONS):
        command = 101+i
        left, top, right, bottom = PICKER_HITS[command]
        active = selected == key
        rounded((left, top, right, bottom), 6,
                '#fce2ee' if active else '#fff0f6' if command == hover else '#fffafd',
                '#d68daa' if active else '#edc5d6' if command == hover else '#f0dce5',
                1.5 if active else 1)
        image = library.image(key, round(40*factor))
        canvas.alpha_composite(image, (round((left+right)*factor/2-image.width/2),
                                        round((top+23)*factor-image.height/2)))
        text((left+right)/2, top+44, label, 8.5, '#824b65' if active else '#957285', active, 'mt')
        if active:
            rounded((right-13, top+3, right-3, top+13), 5, '#cd84a4')
            text(right-8, top+2, '✓', 8, '#ffffff', True, 'mt')
    text(88, 226, '5 秒后自动消失', 8.5, '#b18498', anchor='mt')
    return canvas.resize((round(PICKER_WIDTH*dpi), round(PICKER_HEIGHT*dpi)), Image.Resampling.LANCZOS)


class ExpressionPicker(PinkMenu):
    logical_width, logical_height = PICKER_WIDTH, PICKER_HEIGHT
    hits = PICKER_HITS
    commands = (51, 52, *range(101, 110))
    title = '茜特菈莉 · 今天的心情'

    def state(self):
        return {'expression': self.owner.expression_key}

    def render_pixels(self, state, hover, dpi):
        return rgba_pixels(render_picker(self.owner.stickers, state, hover, dpi))

    def invoke(self, command):
        origin = (self.x+12, self.y+10)
        if command == 52:
            self.owner.show_expression(None)
            self.paint()
            return
        self.close()
        if command == 51:
            self.owner.menu(position=origin)
        else:
            self.owner.show_expression(EXPRESSIONS[command-101][0])

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == 0x0100 and wparam in (37, 38, 39, 40) and self.hover in range(101, 110):
            self.keyboard = True
            step = {37: -1, 38: -3, 39: 1, 40: 3}[wparam]
            self.hover = 101+(self.hover-101+step) % 9
            self.paint()
            return 0
        return super().window_proc(hwnd, message, wparam, lparam)


class ExpressionBadge(PinkMenu):
    """No focus or mouse capture: the sticker never interrupts dragging/playback."""
    activate = False
    beside_pet = False
    extra_style = 0x08000000 | 0x00000020  # NOACTIVATE | TRANSPARENT
    title = '茜特菈莉 · 表情'

    def __init__(self, owner, api, key):
        super().__init__(owner, api)
        self.key = key

    def dimensions(self):
        edge = round(136*self.owner.scale)
        return edge, edge

    def state(self):
        return {'key': self.key}

    def render_pixels(self, state, hover, dpi):
        image = self.owner.stickers.image(state['key'], self.width-8)
        canvas = Image.new('RGBA', (self.width, self.height))
        canvas.alpha_composite(image, ((self.width-image.width)//2, (self.height-image.height)//2))
        return rgba_pixels(canvas)

    def follow(self):
        a, owner = self.api, self.owner
        pose = owner.visual_pose
        placement = (owner.x, owner.y, owner.scale, pose)
        if getattr(self, 'placement', None) == placement:
            return
        self.placement = placement
        # Use one fixed pose boundary, not a changing frame bbox: no breathing jitter.
        right, top = owner.expression_anchors[pose]
        x = owner.x+round(right*owner.scale)+round(10*owner.scale)
        y = owner.y+round(top*owner.scale)-round(self.height*.66)
        monitor = monitor_work_area(a, owner.x+owner.width//2, owner.y+owner.height//2)
        x = max(monitor.left+4, min(x, monitor.right-self.width-4))
        y = max(monitor.top+4, min(y, monitor.bottom-self.height-4))
        if (x, y) != (self.x, self.y):
            self.x, self.y = x, y
            a.user.SetWindowPos(self.hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == 0x0084:
            return -1  # HTTRANSPARENT, including opaque parts of the sticker.
        if message == 0x0021:
            return 3  # MA_NOACTIVATE
        if message in (0x0006, 0x0200, 0x0201, 0x0202, 0x0205):
            return 0
        return super().window_proc(hwnd, message, wparam, lparam)
