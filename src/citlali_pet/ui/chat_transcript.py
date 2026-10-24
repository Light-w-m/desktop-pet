"""Scrollable native text bubbles; message contents never become actions."""
import ctypes as C
from ctypes import wintypes as W
from .chat_images import paint_image


class SCROLLINFO(C.Structure):
    _fields_ = [('cbSize', W.UINT), ('fMask', W.UINT), ('nMin', C.c_int),
                ('nMax', C.c_int), ('nPage', W.UINT), ('nPos', C.c_int), ('nTrackPos', C.c_int)]


class PAINTSTRUCT(C.Structure):
    _fields_ = [('hdc', W.HDC), ('erase', W.BOOL), ('rect', W.RECT),
                ('restore', W.BOOL), ('update', W.BOOL), ('reserved', W.BYTE*32)]


def rgb(value):
    r, g, b = bytes.fromhex(value.lstrip('#'))
    return r | g << 8 | b << 16


class BubbleTranscript:
    COLOURS = {'user': '#f3dbe8', 'assistant': '#ffffff', 'notice': '#eee8ed'}

    def __init__(self, chat, hwnd):
        self.chat, self.api, self.hwnd = chat, chat.api, hwnd
        self.bubbles = []
        self.offset = self.maximum = self.content_height = 0
        self.laying_out = False
        self.wheel_remainder = 0
        a = self.api
        for name, result, arguments in (
            ('InvalidateRect', W.BOOL, (W.HWND, C.POINTER(W.RECT), W.BOOL)),
            ('BeginPaint', W.HDC, (W.HWND, C.POINTER(PAINTSTRUCT))),
            ('EndPaint', W.BOOL, (W.HWND, C.POINTER(PAINTSTRUCT))),
            ('ShowScrollBar', W.BOOL, (W.HWND, C.c_int, W.BOOL)),
            ('SetScrollInfo', C.c_int, (W.HWND, C.c_int, C.POINTER(SCROLLINFO), W.BOOL)),
            ('GetScrollInfo', W.BOOL, (W.HWND, C.c_int, C.POINTER(SCROLLINFO))),
        ):
            a.signature(a.user, name, result, *arguments)
        a.signature(a.gdi, 'GetTextExtentPoint32W', W.BOOL, W.HDC, W.LPCWSTR, C.c_int, C.POINTER(W.SIZE))
        a.signature(a.gdi, 'FillRgn', W.BOOL, W.HDC, W.HRGN, W.HBRUSH)
        self.brushes = {role: a.gdi.CreateSolidBrush(rgb(value)) for role, value in self.COLOURS.items()}
        self.callback = a.WNDPROC(self.window_proc)
        self.original = a.user.SetWindowLongPtrW(hwnd, -4, C.cast(self.callback, C.c_void_p).value)
        self.bubble_callback = a.WNDPROC(self.bubble_proc)

    def contains(self, hwnd):
        return hwnd == self.hwnd or any(item['hwnd'] == hwnd for item in self.bubbles)

    def set_records(self, records):
        a = self.api
        bottom = self.offset >= self.maximum - round(2*self.chat.dpi)
        for item in self.bubbles:
            a.user.DestroyWindow(item['hwnd'])
        self.bubbles.clear()
        messages = list(records[-20:]) or [('assistant', '我在这里。想聊点什么？')]
        # The window text also exposes plain message bodies to accessibility
        # readers and WM_GETTEXT. Sender names are never inserted into the view.
        a.user.SetWindowTextW(self.hwnd, '\r\n\r\n'.join(('[图片]\r\n' if len(record)>2 and record[2] else '')+record[1] for record in messages)[-24000:])
        for record in messages:
            role,text = record[:2]
            image = record[2] if len(record)>2 else None
            role = role if role in self.COLOURS else 'notice'
            text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')
            style = 0x50000844 | (1 if role == 'notice' else 0)  # multiline, read-only, no HTML or links
            hwnd = a.user.CreateWindowExW(0, 'EDIT', text, style, 0, 0, 1, 1,
                self.hwnd, None, self.chat.owner.instance, None)
            if not hwnd:
                raise C.WinError(C.get_last_error())
            a.user.SendMessageW(hwnd, 0x0030, self.chat.font, 0)
            original = a.user.SetWindowLongPtrW(hwnd, -4, C.cast(self.bubble_callback, C.c_void_p).value)
            self.bubbles.append({'hwnd': hwnd, 'role': role, 'text': text, 'original': original,'image':image})
        self.layout(bottom or messages[-1][0] == 'user')

    def measure(self, width):
        """Use the EDIT's own wrapped line count, including long URLs and CJK."""
        a, dpi = self.api, self.chat.dpi
        margin, px, py, gap = [max(1, round(v*dpi)) for v in (10, 11, 9, 12)]
        max_width = max(1, round((width-2*margin)*.82))
        dc = a.user.GetDC(self.hwnd)
        previous = a.gdi.SelectObject(dc, self.chat.font)
        size = W.SIZE()
        a.gdi.GetTextExtentPoint32W(dc, '国Ag', 3, C.byref(size))
        line_height = size.cy
        y = margin
        try:
            for item in self.bubbles:
                natural = 0
                for line in item['text'].splitlines() or ['']:
                    units = len(line.encode('utf-16-le', errors='surrogatepass'))//2
                    a.gdi.GetTextExtentPoint32W(dc, line, units, C.byref(size))
                    natural = max(natural, size.cx)
                bubble_width = min(max_width, max(round(40*dpi), natural+2*px))
                preview = item['image'].preview((max(1,max_width-2*px),round(122*dpi))) if item.get('image') else None
                if preview:bubble_width = max(bubble_width,preview[0][0]+2*px)
                image_space = preview[0][1]+(round(8*dpi) if item['text'] else 0) if preview else 0
                x = width-margin-bubble_width if item['role'] == 'user' else margin
                if item['role'] == 'notice':x = (width-bubble_width)//2
                hwnd = item['hwnd']
                text_width = max(1, bubble_width-2*px)
                a.user.SetWindowPos(hwnd, None, x+px, y+py-self.offset, text_width, round(48*dpi), 0x0014)
                # Set the wrap width explicitly before counting *all* lines.
                rect = W.RECT(0, 0, text_width, 1000000)
                a.user.SendMessageW(hwnd, 0x00B4, 0, C.addressof(rect))
                lines = max(1, a.user.SendMessageW(hwnd, 0x00BA, 0, 0))
                text_height = lines*line_height+2 if item['text'] else 0
                height = text_height+2*py+image_space
                item.update(x=x, y=y, width=bubble_width, height=height, lines=lines, px=px, py=py,
                            preview=preview,image_space=image_space,text_height=text_height)
                a.user.SetWindowPos(hwnd, None, x+px, y+py+image_space-self.offset, text_width, max(1,text_height), 0x0014)
                a.user.ShowWindow(hwnd,5 if item['text'] else 0)
                rect.bottom = max(1,text_height)
                a.user.SendMessageW(hwnd, 0x00B3, 0, C.addressof(rect))
                y += height+gap
        finally:
            a.gdi.SelectObject(dc, previous)
            a.user.ReleaseDC(self.hwnd, dc)
        return y-gap+margin

    def layout(self, bottom=False):
        if self.laying_out:return
        self.laying_out = True
        a = self.api
        try:
            a.user.ShowScrollBar(self.hwnd, 1, False)
            rect = W.RECT()
            a.user.GetClientRect(self.hwnd, C.byref(rect))
            self.content_height = self.measure(rect.right)
            if self.content_height > rect.bottom:
                a.user.ShowScrollBar(self.hwnd, 1, True)
                a.user.GetClientRect(self.hwnd, C.byref(rect))
                self.content_height = self.measure(rect.right)
            self.maximum = max(0, self.content_height-rect.bottom)
            self.offset = self.maximum if bottom else min(self.maximum, self.offset)
            info = SCROLLINFO(C.sizeof(SCROLLINFO), 0x07, 0, max(0, self.content_height-1), rect.bottom, self.offset, 0)
            a.user.SetScrollInfo(self.hwnd, 1, C.byref(info), True)
            self.place_bubbles()
        finally:self.laying_out = False

    def place_bubbles(self):
        for item in self.bubbles:
            self.api.user.SetWindowPos(item['hwnd'], None, item['x']+item['px'], item['y']+item['py']+item['image_space']-self.offset,
                item['width']-2*item['px'], max(1,item['text_height']), 0x0014)
        self.api.user.InvalidateRect(self.hwnd, None, True)

    def scroll_to(self, offset):
        offset = max(0, min(self.maximum, round(offset)))
        if offset == self.offset:return
        self.offset = offset
        info = SCROLLINFO(C.sizeof(SCROLLINFO), 0x04, 0, 0, 0, offset, 0)
        self.api.user.SetScrollInfo(self.hwnd, 1, C.byref(info), True)
        self.place_bubbles()

    def mouse_wheel(self, wparam):
        self.wheel_remainder += C.c_short((wparam>>16)&0xffff).value
        steps = int(self.wheel_remainder/120)
        self.wheel_remainder -= steps*120
        self.scroll_to(self.offset-steps*round(54*self.chat.dpi))

    def paint(self, dc):
        a = self.api
        rect = W.RECT()
        a.user.GetClientRect(self.hwnd, C.byref(rect))
        a.user.FillRect(dc, C.byref(rect), self.chat.brush)
        for item in self.bubbles:
            top = item.get('y', 0)-self.offset
            if 'width' not in item or top+item['height'] <= 0 or top >= rect.bottom:continue
            region = a.gdi.CreateRoundRectRgn(item['x'], top, item['x']+item['width']+1,
                top+item['height']+1, round(14*self.chat.dpi), round(14*self.chat.dpi))
            a.gdi.FillRgn(dc, region, self.brushes[item['role']])
            a.gdi.DeleteObject(region)
            if item.get('preview'):paint_image(a,dc,item['preview'],item['x']+item['px'],top+item['py'])

    def window_proc(self, hwnd, message, wparam, lparam):
        a = self.api
        if message == 0x000F:
            paint = PAINTSTRUCT()
            dc = a.user.BeginPaint(hwnd, C.byref(paint))
            self.paint(dc)
            a.user.EndPaint(hwnd, C.byref(paint))
            return 0
        if message in (0x0014, 0x0318):
            self.paint(wparam)
            return 1
        if message == 0x0317:return a.user.DefWindowProcW(hwnd, message, wparam, lparam)
        if message == 0x0111:return 0
        if message == 0x0138:
            item = next((item for item in self.bubbles if item['hwnd'] == lparam), None)
            if item:
                a.gdi.SetBkColor(wparam, rgb(self.COLOURS[item['role']]))
                a.gdi.SetTextColor(wparam, rgb('#827582' if item['role'] == 'notice' else '#594451'))
                return self.brushes[item['role']]
        if message == 0x0005 and self.bubbles:self.layout()
        if message == 0x020A:
            self.mouse_wheel(wparam)
            return 0
        if message == 0x0115:
            command = wparam&0xffff
            rect = W.RECT()
            a.user.GetClientRect(hwnd, C.byref(rect))
            line, page = round(20*self.chat.dpi), max(1, rect.bottom-round(20*self.chat.dpi))
            position = {0:self.offset-line, 1:self.offset+line, 2:self.offset-page,
                        3:self.offset+page, 6:0, 7:self.maximum}.get(command, self.offset)
            if command in (4, 5):
                info = SCROLLINFO(C.sizeof(SCROLLINFO), 0x10)
                a.user.GetScrollInfo(hwnd, 1, C.byref(info))
                position = info.nTrackPos
            self.scroll_to(position)
            return 0
        return a.user.CallWindowProcW(self.original, hwnd, message, wparam, lparam)

    def bubble_proc(self, hwnd, message, wparam, lparam):
        item = next((item for item in self.bubbles if item['hwnd'] == hwnd), None)
        if message == 0x020A:
            self.mouse_wheel(wparam)
            return 0
        if item:return self.api.user.CallWindowProcW(item['original'], hwnd, message, wparam, lparam)
        return self.api.user.DefWindowProcW(hwnd, message, wparam, lparam)

    def dispose(self):
        # The owning chat has already destroyed all the child windows.
        self.bubbles.clear()
        for brush in self.brushes.values():self.api.gdi.DeleteObject(brush)
        self.brushes.clear()
