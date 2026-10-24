"""A native modeless chat card beside the pet; answers are inert plain text."""
import ctypes as C
from ctypes import wintypes as W
import queue
import threading

from . import deepseek
from .chat_transcript import BubbleTranscript
from .chat_images import ImageError, ImageMessage, choose_image, load_image, paint_image
from .pet_menu import monitor_work_area, place_beside


def color(hex_value):
    value = hex_value.lstrip('#')
    r, g, b = (int(value[i:i+2], 16) for i in (0, 2, 4))
    return r | g << 8 | b << 16


class DRAWITEM(C.Structure):
    _fields_ = [('type', W.UINT), ('id', W.UINT), ('item', W.UINT), ('action', W.UINT),
                ('state', W.UINT), ('hwnd', W.HWND), ('dc', W.HDC), ('rect', W.RECT), ('data', C.c_size_t)]


class ChatWindow:
    TITLE = '茜特菈莉 · 聊天'
    WIDTH, HEIGHT = 340, 442
    SEND, CLEAR, SETTINGS, CLOSE, SAVE, BACK = 701, 702, 703, 704, 705, 706
    INPUT, TRANSCRIPT, KEY = 707, 708, 709
    IMAGE, THUMBNAIL, REMOVE_IMAGE = 710, 711, 712

    def __init__(self, owner, api):
        self.owner, self.api = owner, api
        self.hwnd = None
        self.controls = {}
        self.transcript = None
        self.history = []
        self.records = []
        self.results = queue.SimpleQueue()
        self.image_results = queue.SimpleQueue()
        self.attachment = self.attachment_preview = None
        self.preparing_image = False
        self.modal_depth = 0
        self.draft = ''
        self.busy = False
        self.settings_visible = False
        self.status = ''
        self.composing = False
        self.suppress_enter = False
        self.font = self.bold_font = self.brush = self.white_brush = None

    def bind_api(self):
        a = self.api
        for name, result, arguments in (
            ('SendMessageW', a.LRESULT, (W.HWND,W.UINT,a.WPARAM,a.LPARAM)),
            ('PostMessageW', W.BOOL, (W.HWND,W.UINT,a.WPARAM,a.LPARAM)),
            ('SetWindowTextW', W.BOOL, (W.HWND,W.LPCWSTR)),
            ('GetWindowTextLengthW', C.c_int, (W.HWND,)),
            ('GetWindowTextW', C.c_int, (W.HWND,W.LPWSTR,C.c_int)),
            ('SetFocus', W.HWND, (W.HWND,)),
            ('GetFocus', W.HWND, ()),
            ('GetKeyState', C.c_short, (C.c_int,)),
            ('EnableWindow', W.BOOL, (W.HWND,W.BOOL)),
            ('GetDpiForWindow', W.UINT, (W.HWND,)),
            ('SetWindowLongPtrW', C.c_ssize_t, (W.HWND,C.c_int,C.c_ssize_t)),
            ('CallWindowProcW', a.LRESULT, (C.c_void_p,W.HWND,W.UINT,a.WPARAM,a.LPARAM)),
            ('FillRect', C.c_int, (W.HDC,C.POINTER(W.RECT),W.HBRUSH)),
            ('GetClientRect', W.BOOL, (W.HWND,C.POINTER(W.RECT))),
            ('DrawTextW', C.c_int, (W.HDC,W.LPCWSTR,C.c_int,C.POINTER(W.RECT),W.UINT)),
            ('SetWindowRgn', C.c_int, (W.HWND,W.HRGN,W.BOOL)),
        ):
            a.signature(a.user, name, result, *arguments)
        a.signature(a.gdi,'CreateSolidBrush',W.HBRUSH,W.DWORD)
        a.signature(a.gdi,'CreateRoundRectRgn',W.HRGN,C.c_int,C.c_int,C.c_int,C.c_int,C.c_int,C.c_int)
        a.signature(a.gdi,'SetBkMode',C.c_int,W.HDC,C.c_int)
        a.signature(a.gdi,'SetBkColor',W.DWORD,W.HDC,W.DWORD)
        a.signature(a.gdi,'SetTextColor',W.DWORD,W.HDC,W.DWORD)
        a.signature(a.gdi,'CreateFontW',W.HFONT,*([C.c_int]*5),*([W.DWORD]*8),W.LPCWSTR)

    def text(self, name):
        hwnd = self.controls[name]
        buffer = C.create_unicode_buffer(self.api.user.GetWindowTextLengthW(hwnd)+1)
        self.api.user.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def set_text(self, name, value):
        if self.hwnd:
            self.api.user.SetWindowTextW(self.controls[name], value)

    def add_control(self, name, kind, text, rect, extra=0, command=0, bold=False):
        a = self.api
        x,y,width,height = [round(v*self.dpi) for v in rect]
        hwnd = a.user.CreateWindowExW(0, kind, text, 0x50000000 | extra,
            x,y,width,height,self.hwnd,command,self.owner.instance,None)
        if not hwnd:
            raise C.WinError(C.get_last_error())
        self.controls[name] = hwnd
        a.user.SendMessageW(hwnd,0x0030,self.bold_font if bold else self.font,1)
        return hwnd

    def open(self):
        a = self.api
        if self.hwnd:
            a.user.ShowWindow(self.hwnd,5)
            a.user.SetForegroundWindow(self.hwnd)
            a.user.SetFocus(self.controls['key' if self.settings_visible else 'input'])
            return
        self.bind_api()
        self.dpi = max(1,a.user.GetDpiForWindow(self.owner.hwnd)/96)
        bounds = self.owner.popup_bounds()
        area = monitor_work_area(a,(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
        self.dpi *= min(1,(area.bottom-area.top-12)/(self.HEIGHT*self.dpi),
                        (area.right-area.left-12)/(self.WIDTH*self.dpi))
        self.width, self.height = round(self.WIDTH*self.dpi), round(self.HEIGHT*self.dpi)
        x,y = self.position()
        self.hwnd = a.user.CreateWindowExW(0x00000008 | 0x00000080,
            'CitlaliDesktopPetWindow_20261014',self.TITLE,0x80000000 | 0x02000000,
            x,y,self.width,self.height,self.owner.hwnd,None,self.owner.instance,None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.controls = {}
        self.brush = a.gdi.CreateSolidBrush(color('#fff8fb'))
        self.white_brush = a.gdi.CreateSolidBrush(color('#ffffff'))
        self.font = a.gdi.CreateFontW(-round(13*self.dpi),0,0,0,400,0,0,0,1,0,0,5,0,'Microsoft YaHei UI')
        self.bold_font = a.gdi.CreateFontW(-round(15*self.dpi),0,0,0,600,0,0,0,1,0,0,5,0,'Microsoft YaHei UI')
        self.add_control('title','STATIC','茜特菈莉 · 聊天',(16,13,192,25),bold=True)
        self.add_control('settings','BUTTON','设置',(236,11,52,27),0x0001000b,self.SETTINGS)
        self.add_control('close','BUTTON','×',(296,11,28,27),0x0001000b,self.CLOSE)
        self.add_control('subtitle','STATIC','DeepSeek · 对话与识图',(16,43,300,20))
        transcript = self.add_control('transcript','STATIC','',(16,70,308,224),
            0x02000000 | 0x00200000,self.TRANSCRIPT)
        self.transcript = BubbleTranscript(self,transcript)
        input_hwnd = self.add_control('input','EDIT',self.draft,(16,306,308,58),
            0x00010000 | 0x00000004 | 0x00000040 | 0x00001000,self.INPUT)
        a.user.SendMessageW(input_hwnd,0x00C5,deepseek.MAX_INPUT,0)
        self.input_callback = a.WNDPROC(self.input_proc)
        self.input_original = a.user.SetWindowLongPtrW(input_hwnd,-4,C.cast(self.input_callback,C.c_void_p).value)
        self.add_control('status','STATIC',self.status,(16,374,308,20))
        self.add_control('attachment_preview','STATIC','',(16,372,28,28),0x0000000d,self.THUMBNAIL)
        self.add_control('attachment_name','STATIC','',(52,378,226,20),0x0000408c)
        self.add_control('remove_image','BUTTON','×',(292,372,32,28),0x0001000b,self.REMOVE_IMAGE)
        self.add_control('clear','BUTTON','清空',(16,401,64,27),0x0001000b,self.CLEAR)
        self.add_control('image','BUTTON','图片',(88,401,64,27),0x0001000b,self.IMAGE)
        self.add_control('send','BUTTON','发送',(246,401,78,27),0x0001000b,self.SEND,bold=True)
        self.add_control('key_label','STATIC','DeepSeek API Key',(16,83,308,24),bold=True)
        key_hwnd = self.add_control('key','EDIT','',(16,121,308,32),0x00010000 | 0x00800000 | 0x0020 | 0x0080,self.KEY)
        a.user.SendMessageW(key_hwnd,0x00C5,256,0)
        self.add_control('key_info','STATIC','密钥只保存在本机，并由 Windows 加密。\n图片仅在你选图并发送后提交。',(16,171,308,54))
        self.add_control('key_status','STATIC','',(16,239,308,42))
        self.add_control('save','BUTTON','保存',(218,306,106,32),0x0001000b,self.SAVE)
        self.add_control('back','BUTTON','返回聊天',(16,306,106,32),0x0001000b,self.BACK)
        region = a.gdi.CreateRoundRectRgn(0,0,self.width+1,self.height+1,round(18*self.dpi),round(18*self.dpi))
        if not a.user.SetWindowRgn(self.hwnd,region,True):a.gdi.DeleteObject(region)
        self.show_settings(False)
        self.render_transcript()
        self.refresh_busy()
        a.user.ShowWindow(self.hwnd,4 if self.owner.qa_mode else 5)
        if not self.owner.qa_mode:a.user.SetFocus(input_hwnd)
        self.placement = None
        self.follow()

    def position(self):
        bounds = self.owner.popup_bounds()
        area = monitor_work_area(self.api,(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
        return place_beside(bounds,(self.width,self.height),area,round(12*self.dpi))

    def follow(self):
        placement = (self.owner.x,self.owner.y,self.owner.scale,self.owner.visual_pose)
        if not self.hwnd or getattr(self,'placement',None) == placement:
            return
        self.placement = placement
        x,y = self.position()
        self.api.user.SetWindowPos(self.hwnd,None,x,y,0,0,0x0001 | 0x0004 | 0x0010)

    def render_transcript(self):
        if not self.hwnd:return
        self.transcript.set_records(self.records)

    def show_settings(self, visible):
        self.settings_visible = visible
        for name in ('transcript','input','status','clear','image','send'):
            self.api.user.ShowWindow(self.controls[name],0 if visible else 5)
        for name in ('key_label','key','key_info','key_status','save','back'):
            self.api.user.ShowWindow(self.controls[name],5 if visible else 0)
        self.refresh_attachment()
        if visible:
            self.set_text('key','')
            try:
                deepseek.load_api_key()
                status = '已配置密钥。留空返回，或输入新密钥更新。'
            except deepseek.ChatError:
                status = '尚未配置密钥，请填写后保存。'
            self.set_text('key_status',status)
        if not self.owner.qa_mode:
            self.api.user.SetFocus(self.controls['key' if visible else 'input'])

    def refresh_busy(self):
        if not self.hwnd:return
        for name in ('send','input','clear','image','remove_image'):
            self.api.user.EnableWindow(self.controls[name],not self.busy and not self.preparing_image)
        self.set_text('send','等待…' if self.busy else '发送')
        self.set_text('status',self.status)

    def refresh_attachment(self):
        if not self.hwnd:return
        visible = bool(self.attachment) and not self.settings_visible
        if self.attachment:
            self.attachment_preview = self.attachment.preview((round(28*self.dpi),round(28*self.dpi)))
        else:self.attachment_preview = None
        for name in ('attachment_preview','attachment_name','remove_image'):
            self.api.user.ShowWindow(self.controls[name],5 if visible else 0)
        self.api.user.ShowWindow(self.controls['status'],0 if visible or self.settings_visible else 5)
        self.set_text('attachment_name',self.attachment.name if self.attachment else '')
        self.api.user.InvalidateRect(self.controls['attachment_preview'],None,True)

    def attach_image(self, path):
        if self.busy or self.preparing_image:return
        self.preparing_image = True
        self.status = '正在准备图片…'
        self.refresh_busy()
        def worker():
            try:self.image_results.put((load_image(path),None))
            except ImageError as error:self.image_results.put((None,str(error)))
            except Exception:self.image_results.put((None,'图片准备失败，请换一张图片。'))
        threading.Thread(target=worker,name='PetImagePrepare',daemon=True).start()

    def pick_image(self):
        if self.busy or self.preparing_image:return
        self.modal_depth += 1
        self.api.user.SetTimer(self.owner.hwnd,1,16,None)
        try:
            path = choose_image(self.hwnd)
            if path:self.attach_image(path)
        except ImageError as error:
            self.status = str(error)
            self.refresh_busy()
        finally:
            self.api.user.KillTimer(self.owner.hwnd,1)
            self.modal_depth -= 1

    def send(self):
        if self.busy or self.preparing_image:return
        question = self.text('input').strip()
        if self.attachment:question = ImageMessage(question,self.attachment)
        try:
            deepseek.build_request(question,self.history)
            deepseek.load_api_key()
        except deepseek.ChatError as error:
            self.records.append(('notice',str(error)))
            self.records = self.records[-20:]
            self.render_transcript()
            self.status = '请检查输入或 API Key 设置。'
            self.refresh_busy()
            return
        self.busy = True
        self.status = '正在听你说话…'
        self.records.append(('user',deepseek.message_text(question),self.attachment))
        self.attachment = None
        self.refresh_attachment()
        self.set_text('input','')
        self.draft = ''
        self.render_transcript()
        self.refresh_busy()
        history = list(self.history)

        def worker():
            try:
                self.results.put((question,deepseek.ask(question,history),None))
            except deepseek.ChatError as error:
                self.results.put((question,None,str(error)))
            except Exception:
                self.results.put((question,None,'这次连接没有完成，请稍后重试。'))
        threading.Thread(target=worker,name='PetTextChat',daemon=True).start()

    def poll(self):
        try:
            image,error = self.image_results.get_nowait()
        except queue.Empty:pass
        else:
            self.preparing_image = False
            if error:
                self.status = error
                self.records.append(('notice',error))
                self.records = self.records[-20:]
                self.render_transcript()
            else:
                self.attachment = image
                self.status = ''
            self.refresh_attachment()
            self.refresh_busy()
        try:
            question,answer,error = self.results.get_nowait()
        except queue.Empty:
            return
        self.busy = False
        if error:
            self.records.append(('notice',error))
            self.status = '发送失败，可以重试。'
            self.set_text('input',deepseek.message_text(question))
            self.draft = deepseek.message_text(question)
            if isinstance(question,ImageMessage):self.attachment = question.image
        else:
            self.history.append((question,answer))
            self.history = self.history[-8:]
            self.records.append(('assistant',answer))
            self.status = ''
        self.records = self.records[-20:]
        self.render_transcript()
        self.refresh_attachment()
        self.refresh_busy()
        if self.hwnd and not self.settings_visible and not self.owner.qa_mode:
            # Do not steal focus if the user has returned to another application.
            if self.api.user.GetFocus() in self.controls.values():
                self.api.user.SetFocus(self.controls['input'])

    def invoke(self, command):
        if command == self.SEND:self.send()
        elif command == self.CLOSE:self.close()
        elif command == self.CLEAR and not self.busy:
            self.records.clear()
            self.history.clear()
            self.attachment = None
            self.status = ''
            self.refresh_attachment()
            self.refresh_busy()
            self.render_transcript()
        elif command == self.IMAGE:self.pick_image()
        elif command == self.REMOVE_IMAGE and not self.busy:
            self.attachment = None
            self.refresh_attachment()
        elif command == self.SETTINGS:self.show_settings(not self.settings_visible)
        elif command == self.BACK:self.show_settings(False)
        elif command == self.SAVE:
            try:
                key = self.text('key').strip()
                if key:deepseek.save_api_key(key)
                else:deepseek.load_api_key()
                self.set_text('key','')
                self.show_settings(False)
                self.status = '密钥已就绪，可以聊天了。'
                self.refresh_busy()
            except (deepseek.ChatError,OSError) as error:
                self.set_text('key_status',str(error) if isinstance(error,deepseek.ChatError) else '保存失败，请检查本机设置目录。')

    def input_proc(self, hwnd, message, wparam, lparam):
        a = self.api
        if message == 0x010D:self.composing = True
        elif message == 0x010E:self.composing = False
        elif message == 0x0100 and wparam == 13 and not self.composing and not a.user.GetKeyState(16)&0x8000:
            self.suppress_enter = True
            a.user.PostMessageW(self.hwnd,0x0111,self.SEND,0)
            return 0
        elif message == 0x0102 and wparam == 13 and self.suppress_enter:
            self.suppress_enter = False
            return 0
        elif message == 0x0100 and wparam == 27 and not self.composing:
            self.close()
            return 0
        return a.user.CallWindowProcW(self.input_original,hwnd,message,wparam,lparam)

    def dialog_key(self, message):
        if not self.hwnd or (message.hWnd != self.hwnd and message.hWnd not in self.controls.values()
                             and not self.transcript.contains(message.hWnd)):return False
        if message.message == 0x0100 and message.wParam == 9:
            names = ('key','save','back','settings','close') if self.settings_visible else ('input','send','image','clear','settings','close')
            if self.attachment and not self.settings_visible:names = names+('remove_image',)
            controls = [self.controls[name] for name in names if not (self.busy or self.preparing_image) or name not in ('input','send','clear','image','remove_image')]
            current = self.api.user.GetFocus()
            index = controls.index(current) if current in controls else -1
            step = -1 if self.api.user.GetKeyState(16)&0x8000 else 1
            self.api.user.SetFocus(controls[(index+step)%len(controls)])
            return True
        if message.message == 0x0100 and message.wParam == 27 and not self.composing:
            self.close()
            return True
        return False

    def draw_button(self, item):
        a = self.api
        if item.id == self.THUMBNAIL:
            a.user.FillRect(item.dc,C.byref(item.rect),self.white_brush)
            if self.attachment_preview:paint_image(a,item.dc,self.attachment_preview,0,0)
            return
        label = next((name for name,handle in self.controls.items() if handle == item.hwnd),None)
        text = {'send':'等待…' if self.busy else '发送','clear':'清空','image':'图片','remove_image':'×','settings':'设置','close':'×','save':'保存','back':'返回聊天'}.get(label,'')
        strong = label in ('send','save') and not item.state&4
        brush = a.gdi.CreateSolidBrush(color('#bb7394' if strong else '#f8e5ee'))
        a.user.FillRect(item.dc,C.byref(item.rect),brush)
        a.gdi.DeleteObject(brush)
        a.gdi.SetBkMode(item.dc,1)
        a.gdi.SetTextColor(item.dc,color('#ffffff' if strong else '#8b6278'))
        old = a.gdi.SelectObject(item.dc,self.font)
        a.user.DrawTextW(item.dc,text,-1,C.byref(item.rect),0x01 | 0x04 | 0x20)
        a.gdi.SelectObject(item.dc,old)

    def window_proc(self, hwnd, message, wparam, lparam):
        a = self.api
        if message == 0x0006 and (wparam&0xffff) == 0 and not self.modal_depth:
            # Defer destruction until Windows finishes transferring activation.
            a.user.PostMessageW(hwnd,0x8047,0,0)
            return 0
        if message == 0x8047:
            if not self.modal_depth:self.close()
            return 0
        if message == 0x0111:
            if not (wparam>>16):self.invoke(wparam&0xffff)
            return 0
        if message == 0x0010:
            self.close()
            return 0
        if message in (0x0002,0x0082):return 0
        if message == 0x0014:
            rect = W.RECT()
            a.user.GetClientRect(hwnd,C.byref(rect))
            a.user.FillRect(wparam,C.byref(rect),self.brush)
            return 1
        if message in (0x0133,0x0138):
            white = lparam in (self.controls.get('transcript'),self.controls.get('input'),self.controls.get('key'))
            a.gdi.SetBkColor(wparam,color('#ffffff' if white else '#fff8fb'))
            a.gdi.SetTextColor(wparam,color('#694c5d'))
            return self.white_brush if white else self.brush
        if message == 0x002B:
            self.draw_button(C.cast(lparam,C.POINTER(DRAWITEM)).contents)
            return 1
        return a.user.DefWindowProcW(hwnd,message,wparam,lparam)

    def close(self):
        if not self.hwnd:return
        self.draft = self.text('input')
        self.api.user.DestroyWindow(self.hwnd)
        if self.transcript:self.transcript.dispose()
        self.transcript = None
        self.hwnd = None
        self.controls.clear()
        self.composing = self.suppress_enter = False
        for item in (self.font,self.bold_font,self.brush,self.white_brush):
            if item:self.api.gdi.DeleteObject(item)
        self.font = self.bold_font = self.brush = self.white_brush = None
