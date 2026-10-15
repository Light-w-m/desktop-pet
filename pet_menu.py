"""A non-modal layered context card; the pet keeps playing while it is open."""
import ctypes as C
from ctypes import wintypes as W
from concurrent.futures import ThreadPoolExecutor
import logging

from PIL import Image, ImageChops
from menu_view import COMMANDS, HEIGHT, HITS, WIDTH, font, render_menu

_RENDERER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='PetMenuPaint')


class MONITORINFO(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('monitor', W.RECT), ('work', W.RECT), ('flags', W.DWORD)]


def monitor_work_area(api, x, y):
    api.signature(api.user, 'MonitorFromPoint', W.HANDLE, api.POINT, W.DWORD)
    api.signature(api.user, 'GetMonitorInfoW', W.BOOL, W.HANDLE, C.POINTER(MONITORINFO))
    info = MONITORINFO()
    info.cbSize = C.sizeof(info)
    if not api.user.GetMonitorInfoW(api.user.MonitorFromPoint(api.POINT(x, y), 2), C.byref(info)):
        raise C.WinError(C.get_last_error())
    return info.work


def rgba_pixels(image):
    r, g, b, alpha = image.split()
    return Image.merge('RGBA', (ImageChops.multiply(r, alpha), ImageChops.multiply(g, alpha),
                               ImageChops.multiply(b, alpha), alpha)).tobytes('raw', 'BGRA')


def menu_pixels(state, hover, dpi):
    return rgba_pixels(render_menu(state, hover, dpi))


class PinkMenu:
    logical_width, logical_height = WIDTH, HEIGHT
    commands, hits = COMMANDS, HITS
    activate = True
    extra_style = 0
    title = '茜特菈莉 · 小小日常'

    def __init__(self, owner, api):
        self.owner, self.api = owner, api
        self.hwnd = None
        self.dc = self.bitmap = self.old_bitmap = self.bits = None
        self.hover = None
        self.pressed = None
        self.keyboard = False
        self.closing = False
        self.last_state = None
        self.paint_future = None
        self.paint_dirty = False

    def state(self):
        return {'auto': self.owner.auto, 'requested': self.owner.clock.requested,
                'pending': self.owner.clock.pending, 'paused': self.owner.paused, 'scale': self.owner.scale}

    def dimensions(self):
        return round(self.logical_width*self.dpi), round(self.logical_height*self.dpi)

    def hit_test(self, x, y):
        for command, (left, top, right, bottom) in self.hits.items():
            if left <= x < right and top <= y < bottom:
                return command
        return None

    def render_pixels(self, state, hover, dpi):
        return menu_pixels(state, hover, dpi)

    def open(self, x, y):
        a = self.api
        a.signature(a.user, 'GetDpiForWindow', W.UINT, W.HWND)
        a.signature(a.user, 'SetFocus', W.HWND, W.HWND)
        a.signature(a.user, 'GetKeyState', C.c_short, C.c_int)
        a.signature(a.user, 'PostMessageW', W.BOOL, W.HWND, W.UINT, a.WPARAM, a.LPARAM)
        class TRACKMOUSEEVENT(C.Structure):
            _fields_ = [('cbSize', W.DWORD), ('flags', W.DWORD), ('hwnd', W.HWND), ('hoverTime', W.DWORD)]
        self.TRACKMOUSEEVENT = TRACKMOUSEEVENT
        a.signature(a.user, 'TrackMouseEvent', W.BOOL, C.POINTER(TRACKMOUSEEVENT))
        self.dpi = max(1, a.user.GetDpiForWindow(self.owner.hwnd)/96)
        self.width, self.height = self.dimensions()
        work = monitor_work_area(a, x, y)
        self.x = max(work.left, min(x-12, work.right-self.width))
        self.y = max(work.top, min(y-10, work.bottom-self.height))
        self.hwnd = a.user.CreateWindowExW(0x00080000 | 0x00000008 | 0x00000080 | self.extra_style,
            'CitlaliDesktopPetWindow_20261014', self.title, 0x80000000,
            self.x, self.y, self.width, self.height, self.owner.hwnd, None, self.owner.instance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.dc = a.gdi.CreateCompatibleDC(None)
        bmi = a.BITMAPINFO()
        bmi.bmiHeader.biSize = C.sizeof(a.BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = self.width, -self.height
        bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
        self.bits = C.c_void_p()
        self.bitmap = a.gdi.CreateDIBSection(self.dc, C.byref(bmi), 0, C.byref(self.bits), None, 0)
        if not self.dc or not self.bitmap or not self.bits:
            self.close()
            raise C.WinError(C.get_last_error())
        self.old_bitmap = a.gdi.SelectObject(self.dc, self.bitmap)
        self.paint()
        a.user.ShowWindow(self.hwnd, 5 if self.activate else 4)
        if self.activate:
            a.user.SetForegroundWindow(self.hwnd)
            a.user.SetFocus(self.hwnd)
        logging.info('Pink menu opened hwnd=%s', self.hwnd)

    def paint(self):
        self.last_state = self.state()
        self.paint_dirty = True
        self.start_paint()

    def start_paint(self):
        if self.closing or self.paint_future is not None or not self.paint_dirty:
            return
        self.paint_dirty = False
        self.paint_future = _RENDERER.submit(self.render_pixels, self.last_state.copy(), self.hover, self.dpi)
        self.paint_future.add_done_callback(self.paint_ready)

    def paint_ready(self, future):
        if self.hwnd and not self.closing:
            self.api.user.PostMessageW(self.hwnd, 0x8001, 0, 0)

    def finish_paint(self):
        a = self.api
        future = self.paint_future
        if future is None or not future.done():
            return
        pixels = future.result()
        self.paint_future = None
        if self.paint_dirty:
            self.start_paint()
            return
        C.memmove(self.bits, pixels, len(pixels))
        point, size, origin = a.POINT(self.x, self.y), a.SIZE(self.width, self.height), a.POINT(0, 0)
        if not a.user.UpdateLayeredWindow(self.hwnd, None, C.byref(point), C.byref(size), self.dc,
                                         C.byref(origin), 0, C.byref(self.owner.blend), 2):
            raise C.WinError(C.get_last_error())

    def refresh(self):
        if self.hwnd and not self.closing and self.last_state != self.state():
            self.paint()

    def close(self):
        if self.closing:
            return
        self.closing = True
        if self.paint_future:
            self.paint_future.cancel()
            self.paint_future = None
        a = self.api
        if self.hwnd:
            a.user.DestroyWindow(self.hwnd)
        self.hwnd = None
        if self.dc:
            if self.old_bitmap:
                a.gdi.SelectObject(self.dc, self.old_bitmap)
            if self.bitmap:
                a.gdi.DeleteObject(self.bitmap)
            a.gdi.DeleteDC(self.dc)
        self.dc = self.bitmap = self.old_bitmap = self.bits = None
        font.cache_clear()
        if self.owner.popup is self:
            self.owner.popup = None

    def invoke(self, command):
        origin = (self.x+12, self.y+10)
        self.close()
        self.owner.menu_command(command, origin)

    def window_proc(self, hwnd, message, wparam, lparam):
        a = self.api
        if message == 0x8001:
            self.finish_paint()
            return 0
        if message in (0x0002, 0x0082):  # The pet's window owns WM_QUIT.
            return 0
        if message == 0x0006 and (wparam & 0xffff) == 0:  # WA_INACTIVE
            self.close()
            return 0
        if message == 0x0010:
            self.close()
            return 0
        if message == 0x0084:
            return 1
        if message == 0x02A3:
            if not self.keyboard and self.hover is not None:
                self.hover = None
                self.paint()
            return 0
        if message in (0x0200, 0x0201, 0x0202, 0x0205):
            x = C.c_short(lparam & 0xffff).value / self.dpi
            y = C.c_short((lparam >> 16) & 0xffff).value / self.dpi
            command = self.hit_test(x, y)
            if message == 0x0200:
                self.keyboard = False
                track = self.TRACKMOUSEEVENT(C.sizeof(self.TRACKMOUSEEVENT), 2, hwnd, 0)
                a.user.TrackMouseEvent(C.byref(track))
                if command != self.hover:
                    self.hover = command
                    self.paint()
            elif message == 0x0201:
                self.pressed = command
                if command is None:
                    self.close()
            elif message == 0x0202:
                if command and command == self.pressed:
                    self.invoke(command)
                self.pressed = None
            else:
                self.close()
            return 0
        if message == 0x0100:
            if wparam == 27:
                self.close()
            elif wparam in (13, 32):
                if self.hover:
                    self.invoke(self.hover)
            elif wparam in (9, 35, 36, 37, 38, 39, 40):
                self.keyboard = True
                if wparam == 36:
                    self.hover = self.commands[0]
                elif wparam == 35:
                    self.hover = self.commands[-1]
                else:
                    step = -1 if wparam in (37, 38) or (wparam == 9 and a.user.GetKeyState(16) & 0x8000) else 1
                    index = self.commands.index(self.hover) if self.hover in self.commands else (-1 if step > 0 else 0)
                    self.hover = self.commands[(index+step) % len(self.commands)]
                self.paint()
            return 0
        return a.user.DefWindowProcW(hwnd, message, wparam, lparam)
