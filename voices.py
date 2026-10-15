"""A small voice picker and one asynchronous Windows-native playback channel."""
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import logging
import math
import time
import winsound

from PIL import Image, ImageDraw, ImageFilter

from menu_view import font
from pet_menu import PinkMenu, rgba_pixels

WIDTH, HEIGHT, PAGE_SIZE = 188, 244, 6


class VoicePlayer:
    def __init__(self, backend=None):
        self.backend = backend or winsound.PlaySound
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='PetVoice')
        self.future = None
        self.revision = 0
        self.closed = False
        self.current_id = self.deadline = None
        self.duration = 0
        self.error = None

    def _run(self, revision, path):
        if self.closed or revision != self.revision:
            return None
        self.backend(str(path) if path else None,
                     winsound.SND_ASYNC | winsound.SND_FILENAME | winsound.SND_NODEFAULT if path else 0)
        return time.perf_counter()

    def _submit(self, path):
        self.revision += 1
        if self.future:
            self.future.cancel()
        self.future = self.executor.submit(self._run, self.revision, path)

    def play(self, record):
        if self.closed:
            return
        self.current_id, self.duration = record['id'], record['duration_seconds']
        self.deadline = self.error = None
        self._submit(record['path'])

    def stop(self):
        self.current_id = self.deadline = self.error = None
        if not self.closed:
            self._submit(None)

    def poll(self):
        if self.future and self.future.done():
            try:
                started = self.future.result()
                if started is not None and self.current_id is not None:
                    self.deadline = started+self.duration
            except Exception as error:
                logging.warning('Voice playback failed: %s', error)
                self.error = str(error)
                self.current_id = self.deadline = None
            self.future = None
        if self.deadline is not None and time.perf_counter() >= self.deadline:
            self.current_id = self.deadline = None

    def close(self):
        self.revision += 1
        self.closed = True
        if self.future:
            self.future.cancel()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.current_id = self.deadline = None
        try:
            self.backend(None, 0)
        except RuntimeError:
            logging.warning('Could not stop the voice output', exc_info=True)


class VoicePicker(PinkMenu):
    logical_width, logical_height = WIDTH, HEIGHT
    title = '茜特菈莉 · 语音'

    def __init__(self, owner, api):
        super().__init__(owner, api)
        self.records = list(owner.voices.refresh())
        self.page = 0
        self.update_hits()

    @property
    def pages(self):
        return max(1, math.ceil(len(self.records)/PAGE_SIZE))

    def page_records(self, page=None):
        index = self.page if page is None else page
        return self.records[index*PAGE_SIZE:(index+1)*PAGE_SIZE]

    def update_hits(self):
        self.hits = {61:(10,9,48,29), 62:(140,9,178,29),
                     63:(10,201,45,221), 64:(143,201,178,221)}
        self.hits.update({1000+r['id']:(10,38+26*i,178,63+26*i)
                          for i,r in enumerate(self.page_records())})
        self.commands = (61, 62, *(1000+r['id'] for r in self.page_records()), 63, 64)

    def state(self):
        return {'page':self.page,'playing':self.owner.voice_player.current_id,
                'error':self.owner.voice_player.error}

    def change_page(self, step):
        page = max(0, min(self.pages-1, self.page+step))
        if page != self.page:
            self.page = page
            self.hover = self.pressed = None
            self.update_hits()
            self.paint()

    def render_pixels(self, state, hover, dpi):
        return rgba_pixels(self.render(state, hover, dpi))

    def render(self, state, hover, dpi):
        factor = max(2, round(2*dpi))
        canvas = Image.new('RGBA', (WIDTH*factor, HEIGHT*factor))
        draw = ImageDraw.Draw(canvas)
        box = lambda rect:tuple(round(v*factor) for v in rect)

        def rounded(rect, radius, fill, outline=None):
            draw.rounded_rectangle(box(rect),radius=round(radius*factor),fill=fill,
                                   outline=outline,width=factor)

        def text(x, y, label, size=9, fill='#985d7b', bold=False, anchor=None):
            draw.text((round(x*factor),round(y*factor)),label,
                      font=font(round(size*factor),bold),fill=fill,anchor=anchor)

        shadow = Image.new('RGBA', canvas.size)
        ImageDraw.Draw(shadow).rounded_rectangle(box((6,6,182,240)),radius=11*factor,fill=(106,52,76,35))
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3*factor)))
        rounded((4,3,184,240),10,'#fff8fb','#ecc5d5')
        rounded((5,4,183,30),9,'#fce5ee')
        draw.rectangle(box((5,20,183,31)),fill='#fce5ee')
        if hover == 61:
            rounded((10,9,48,29),5,'#f3cfdf')
        text(14,12,'‹ 返回',8.5)
        text(60,10,'语音',10.5,'#824b65',True)
        rounded((140,9,178,29),5,'#f3cfdf' if hover == 62 else '#fff5f9','#eac3d4')
        text(159,12,'停止',8.5,'#985d7b' if state['playing'] else '#b597a6',anchor='mt')
        records = self.page_records(state['page'])
        for i, record in enumerate(records):
            top, bottom = 38+26*i, 63+26*i
            command, active = 1000+record['id'], state['playing'] == record['id']
            rounded((10,top,178,bottom),5,'#f6d5e3' if active else '#fce8f0' if hover == command else '#fffafd',
                    '#df9fba' if active else '#efdae4')
            if active:
                for x, height in ((16,6),(19,11),(22,8)):
                    draw.line([box((x,top+12-height/2)),box((x,top+12+height/2))],fill='#b2698b',width=factor)
            else:
                draw.polygon([box((16,top+8)),box((22,top+12)),box((16,top+16))],fill='#b591a2')
            title = record['title'].rstrip('…')
            title_font = font(round(8.5*factor))
            split = len(title)
            while split > 1 and draw.textlength(title[:split], font=title_font) > 118*factor:
                split -= 1
            lines = (title[:split], title[split:]) if split < len(title) else (title,)
            for j, label in enumerate(lines):
                text(27,top+(2+11*j if len(lines) > 1 else 6),label,8.5,'#824b65' if active else '#957285',active)
            seconds = round(record['duration_seconds'])
            text(173,top+8,f'{seconds//60}:{seconds%60:02}',7.5,'#b18498',anchor='rt')
        if not records:
            text(94,106,'还没有可用语音',10,'#ae8396',anchor='mt')
        for command, rect, label, enabled in (
                (63,(10,201,45,221),'‹',state['page'] > 0),
                (64,(143,201,178,221),'›',state['page']+1 < self.pages)):
            rounded(rect,5,'#f3cfdf' if hover == command and enabled else '#fff5f9','#eac3d4')
            text((rect[0]+rect[2])/2,203,label,11,'#985d7b' if enabled else '#cbb4c0',anchor='mt')
        text(94,206,f"{state['page']+1} / {self.pages}",8.5,'#b18498',anchor='mt')
        text(94,227,'播放失败，请重新点选' if state['error'] else '点击播放 · 滚轮或箭头翻页',7.5,'#b18498',anchor='mt')
        return canvas.resize((round(WIDTH*dpi),round(HEIGHT*dpi)),Image.Resampling.LANCZOS)

    def invoke(self, command):
        if command == 61:
            origin = (self.x+12,self.y+10)
            self.close()
            self.owner.menu(position=origin)
        elif command == 62:
            self.owner.voice_player.stop()
            self.paint()
        elif command in (63,64):
            self.change_page(-1 if command == 63 else 1)
        elif command >= 1000:
            if not self.owner.play_voice(command-1000):
                self.records = list(self.owner.voices.records)
                self.page = min(self.page,self.pages-1)
                self.hover = None
                self.update_hits()
            self.paint()

    def window_proc(self, hwnd, message, wparam, lparam):
        if message == 0x020A:
            self.change_page(-1 if C.c_short((wparam >> 16)&0xffff).value > 0 else 1)
            return 0
        if message == 0x0100 and wparam in (37,39):
            self.change_page(-1 if wparam == 37 else 1)
            return 0
        return super().window_proc(hwnd,message,wparam,lparam)
