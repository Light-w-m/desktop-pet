"""A local Windows desktop pet with per-pixel transparency and original frames."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from bisect import bisect_right
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from PIL import Image, ImageChops, ImageSequence

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', APP_DIR))
ASSETS = APP_DIR / 'assets' if (APP_DIR / 'assets' / 'manifest.json').exists() else RESOURCE_DIR / 'assets'
if '--qa-assets' in sys.argv:
    ASSETS=Path(sys.argv[sys.argv.index('--qa-assets')+1])
SETTINGS = APP_DIR / 'pet-settings.json'
logging.basicConfig(filename=APP_DIR / 'pet.log', level=logging.INFO, format='%(asctime)s %(message)s')

user = C.WinDLL('user32', use_last_error=True)
gdi = C.WinDLL('gdi32', use_last_error=True)
kernel = C.WinDLL('kernel32', use_last_error=True)
winmm = C.WinDLL('winmm', use_last_error=True)
LRESULT = C.c_ssize_t
WPARAM = C.c_size_t
LPARAM = C.c_ssize_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, WPARAM, LPARAM)

class POINT(C.Structure):
    _fields_ = [('x', W.LONG), ('y', W.LONG)]

class SIZE(C.Structure):
    _fields_ = [('cx', W.LONG), ('cy', W.LONG)]

class BLEND(C.Structure):
    _fields_ = [('BlendOp', W.BYTE), ('BlendFlags', W.BYTE), ('SourceConstantAlpha', W.BYTE), ('AlphaFormat', W.BYTE)]

class BITMAPINFOHEADER(C.Structure):
    _fields_ = [('biSize', W.DWORD), ('biWidth', W.LONG), ('biHeight', W.LONG), ('biPlanes', W.WORD), ('biBitCount', W.WORD), ('biCompression', W.DWORD), ('biSizeImage', W.DWORD), ('biXPelsPerMeter', W.LONG), ('biYPelsPerMeter', W.LONG), ('biClrUsed', W.DWORD), ('biClrImportant', W.DWORD)]

class BITMAPINFO(C.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', W.DWORD * 3)]

class WNDCLASS(C.Structure):
    _fields_ = [('style', W.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', C.c_int), ('cbWndExtra', C.c_int), ('hInstance', W.HINSTANCE), ('hIcon', W.HICON), ('hCursor', W.HANDLE), ('hbrBackground', W.HANDLE), ('lpszMenuName', W.LPCWSTR), ('lpszClassName', W.LPCWSTR)]

def signature(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype = result
    fn.argtypes = args
    return fn

signature(kernel, 'GetModuleHandleW', W.HMODULE, W.LPCWSTR)
signature(kernel, 'CreateMutexW', W.HANDLE, C.c_void_p, W.BOOL, W.LPCWSTR)
signature(kernel, 'CloseHandle', W.BOOL, W.HANDLE)
signature(winmm, 'timeBeginPeriod', W.UINT, W.UINT)
signature(winmm, 'timeEndPeriod', W.UINT, W.UINT)
signature(user, 'RegisterClassW', W.ATOM, C.POINTER(WNDCLASS))
signature(user, 'CreateWindowExW', W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HANDLE, W.HINSTANCE, C.c_void_p)
signature(user, 'DefWindowProcW', LRESULT, W.HWND, W.UINT, WPARAM, LPARAM)
signature(user, 'DestroyWindow', W.BOOL, W.HWND)
signature(user, 'ShowWindow', W.BOOL, W.HWND, C.c_int)
signature(user, 'SetTimer', C.c_size_t, W.HWND, C.c_size_t, W.UINT, C.c_void_p)
signature(user, 'KillTimer', W.BOOL, W.HWND, C.c_size_t)
signature(user, 'GetMessageW', W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
signature(user, 'TranslateMessage', W.BOOL, C.POINTER(W.MSG))
signature(user, 'DispatchMessageW', LRESULT, C.POINTER(W.MSG))
signature(user, 'PeekMessageW', W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
signature(user, 'MsgWaitForMultipleObjectsEx', W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.DWORD)
signature(user, 'GetDC', W.HDC, W.HWND)
signature(user, 'ReleaseDC', C.c_int, W.HWND, W.HDC)
signature(user, 'GetCursorPos', W.BOOL, C.POINTER(POINT))
signature(user, 'GetWindowRect', W.BOOL, W.HWND, C.POINTER(W.RECT))
signature(user, 'SetCapture', W.HWND, W.HWND)
signature(user, 'ReleaseCapture', W.BOOL)
signature(user, 'SetWindowPos', W.BOOL, W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT)
signature(user, 'SystemParametersInfoW', W.BOOL, W.UINT, W.UINT, C.c_void_p, W.UINT)
signature(user, 'GetSystemMetrics', C.c_int, C.c_int)
signature(user, 'CreatePopupMenu', W.HANDLE)
signature(user, 'AppendMenuW', W.BOOL, W.HANDLE, W.UINT, C.c_size_t, W.LPCWSTR)
signature(user, 'TrackPopupMenu', W.UINT, W.HANDLE, W.UINT, C.c_int, C.c_int, C.c_int, W.HWND, C.c_void_p)
signature(user, 'DestroyMenu', W.BOOL, W.HANDLE)
signature(user, 'SetForegroundWindow', W.BOOL, W.HWND)
signature(user, 'PostQuitMessage', None, C.c_int)
signature(user, 'MessageBoxW', C.c_int, W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT)
signature(user, 'LoadCursorW', W.HANDLE, W.HINSTANCE, C.c_void_p)
signature(user, 'UpdateLayeredWindow', W.BOOL, W.HWND, W.HDC, C.POINTER(POINT), C.POINTER(SIZE), W.HDC, C.POINTER(POINT), W.DWORD, C.POINTER(BLEND), W.DWORD)
signature(gdi, 'CreateCompatibleDC', W.HDC, W.HDC)
signature(gdi, 'CreateDIBSection', W.HANDLE, W.HDC, C.POINTER(BITMAPINFO), W.UINT, C.POINTER(C.c_void_p), W.HANDLE, W.DWORD)
signature(gdi, 'SelectObject', W.HANDLE, W.HDC, W.HANDLE)
signature(gdi, 'DeleteObject', W.BOOL, W.HANDLE)
signature(gdi, 'DeleteDC', W.BOOL, W.HDC)

class DesktopPet:
    LABELS = {'standing': '站立待机', 'drinking': '坐着喝饮料', 'reading': '趴着读书'}
    # Excerpts repeat briefly, with normal standing between the two idle poses.
    PLAYLIST = [('standing', 12), ('drinking', 6.12), ('standing', 8), ('reading', 4.6)]

    def __init__(self):
        self.settings = {}
        try:
            self.settings = json.loads(SETTINGS.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        self.scale = float(self.settings.get('scale', 1.0))
        self.scale = max(.6, min(1.5, self.scale))
        self.auto = False
        self.paused = False
        self.drag_offset = None
        self.current = 'standing'
        self.playlist_index = 0
        self.last_frame = -1
        self.draw_times = []
        self.render_times = []
        self.frame_index = 0
        self.elapsed = 0.0
        self.last_tick = time.perf_counter()
        self.started = self.last_tick
        self.qa_seconds = float(sys.argv[sys.argv.index('--qa-seconds') + 1]) if '--qa-seconds' in sys.argv else 0
        self.qa_mode = '--qa-seconds' in sys.argv
        self.animations = {}
        self.hwnd = None
        self.dc = self.bitmap = self.old_bitmap = self.bits = None
        self.blend = BLEND(0, 0, 255, 1)
        self.load_frames()
        work = W.RECT()
        if not user.SystemParametersInfoW(0x0030, 0, C.byref(work), 0):
            raise C.WinError(C.get_last_error())
        self.x = int(self.settings.get('x', work.right - self.width - 35))
        self.y = int(self.settings.get('y', work.bottom - self.height))
        self.clamp_position()
        self.callback = WNDPROC(self.window_proc)
        self.instance = kernel.GetModuleHandleW(None)
        classname = 'CitlaliDesktopPetWindow_20261014'
        wc = WNDCLASS()
        wc.lpfnWndProc = self.callback
        wc.hInstance = self.instance
        wc.hCursor = user.LoadCursorW(None, C.c_void_p(32512))
        wc.lpszClassName = classname
        if not user.RegisterClassW(C.byref(wc)):
            raise C.WinError(C.get_last_error())
        # Layered + topmost + tool window: alpha edges, no frame or taskbar button.
        extended_style = 0x00080000 | 0x00000008
        extended_style |= 0x00040000 if '--qa-ui' in sys.argv else 0x00000080
        self.hwnd = user.CreateWindowExW(extended_style, classname, 'Citlali Desktop Pet — 茜特菈莉', 0x80000000, self.x, self.y, self.width, self.height, None, None, self.instance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.create_surface()
        self.draw(0)
        user.ShowWindow(self.hwnd, 4)
        self.last_tick=self.started=time.perf_counter()
        logging.info('Started. hwnd=%s size=%sx%s frames=%s', self.hwnd, self.width, self.height, {k:len(v['frames']) for k,v in self.animations.items()})

    def load_frames(self):
        manifest = json.loads((ASSETS / 'manifest.json').read_text(encoding='utf-8'))
        self.width, self.height = [round(x*self.scale) for x in manifest['canvas']]
        self.animations = {}
        for name, spec in manifest['animations'].items():
            frames=[]
            endpoints=[]
            endpoint=0.0
            with Image.open(ASSETS / spec['file']) as im:
                for f in ImageSequence.Iterator(im):
                    # Animated WebP's durations are available after loading.
                    rgba=f.convert('RGBA')
                    duration=max(1, im.info.get('duration',17))/1000
                    # Scale the entire fixed canvas so subpixel rounding does
                    # not move the sprite when its alpha bounds change.
                    rgba=rgba.resize((self.width,self.height),Image.Resampling.LANCZOS)
                    bbox=rgba.getbbox()
                    if bbox is None:
                        raise ValueError(f'Empty frame: {name}')
                    offset=bbox[:2]
                    size=(bbox[2]-bbox[0],bbox[3]-bbox[1])
                    tile=rgba.crop(bbox)
                    r,g,b,a=tile.split()
                    premult=Image.merge('RGBA',(ImageChops.multiply(r,a),ImageChops.multiply(g,a),ImageChops.multiply(b,a),a))
                    pixels=premult.tobytes('raw','BGRA')
                    frames.append({'pixels':C.create_string_buffer(pixels,len(pixels)),'alpha':a.tobytes(),'offset':offset,'size':size})
                    endpoint+=duration
                    endpoints.append(endpoint)
            self.animations[name]={'frames':frames,'endpoints':endpoints,'duration':endpoint}

    def create_surface(self):
        self.free_surface()
        self.dc=gdi.CreateCompatibleDC(None)
        bmi=BITMAPINFO()
        bmi.bmiHeader.biSize=C.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth=self.width
        bmi.bmiHeader.biHeight=-self.height
        bmi.bmiHeader.biPlanes=1
        bmi.bmiHeader.biBitCount=32
        self.bits=C.c_void_p()
        self.bitmap=gdi.CreateDIBSection(self.dc,C.byref(bmi),0,C.byref(self.bits),None,0)
        if not self.dc or not self.bitmap or not self.bits:
            raise C.WinError(C.get_last_error())
        self.old_bitmap=gdi.SelectObject(self.dc,self.bitmap)

    def free_surface(self):
        if self.dc:
            if self.old_bitmap:gdi.SelectObject(self.dc,self.old_bitmap)
            if self.bitmap:gdi.DeleteObject(self.bitmap)
            gdi.DeleteDC(self.dc)
        self.dc=self.bitmap=self.old_bitmap=self.bits=None

    def draw(self,index):
        render_start=time.perf_counter()
        self.frame_index=index
        frame=self.animations[self.current]['frames'][index]
        C.memset(self.bits,0,self.width*self.height*4)
        x,y=frame['offset']
        w,h=frame['size']
        data=C.addressof(frame['pixels'])
        for row in range(min(h,self.height-y)):
            C.memmove(self.bits.value+((y+row)*self.width+x)*4,data+row*w*4,min(w,self.width-x)*4)
        pt=POINT(self.x,self.y)
        src=POINT(0,0)
        size=SIZE(self.width,self.height)
        if not user.UpdateLayeredWindow(self.hwnd,None,C.byref(pt),C.byref(size),self.dc,C.byref(src),0,C.byref(self.blend),2):
            raise C.WinError(C.get_last_error())
        self.last_frame=index
        if self.qa_mode:
            self.draw_times.append((self.current,index,render_start))
            self.render_times.append(time.perf_counter()-render_start)

    def switch(self,name,automatic=False):
        self.current=name
        self.auto=automatic
        self.elapsed=0
        self.last_frame=-1
        self.last_tick=time.perf_counter()
        logging.info('Animation %s auto=%s',name,automatic)
        self.draw(0)

    def tick(self):
        now=time.perf_counter()
        dt=max(0,now-self.last_tick)
        self.last_tick=now
        if self.qa_seconds and now-self.started>=self.qa_seconds:
            user.DestroyWindow(self.hwnd)
            return
        if self.qa_mode:
            names=['standing','drinking','reading']
            name=names[min(2,int((now-self.started)/max(3,self.qa_seconds/3)))]
            if self.current!=name:self.switch(name,False)
        if self.paused:return
        previous_elapsed=self.elapsed
        self.elapsed+=dt
        duration=self.animations[self.current]['duration']
        # Finish the current loop before changing an automatic idle pose.
        if self.auto and self.elapsed>=self.PLAYLIST[self.playlist_index][1] and int(self.elapsed/duration)>int(previous_elapsed/duration):
            self.playlist_index=(self.playlist_index+1)%len(self.PLAYLIST)
            self.switch(self.PLAYLIST[self.playlist_index][0],True)
        animation=self.animations[self.current]
        t=self.elapsed%animation['duration']
        index=min(bisect_right(animation['endpoints'],t),len(animation['frames'])-1)
        if index!=self.last_frame:self.draw(index)

    def clamp_position(self):
        left=user.GetSystemMetrics(76)
        top=user.GetSystemMetrics(77)
        right=left+user.GetSystemMetrics(78)
        bottom=top+user.GetSystemMetrics(79)
        self.x=max(left,min(self.x,right-self.width))
        self.y=max(top,min(self.y,bottom-self.height))

    def resize(self,scale):
        oldwidth,oldheight=self.width,self.height
        self.scale=max(.6,min(1.5,scale))
        self.load_frames()
        self.x+=(oldwidth-self.width)//2
        self.y+=oldheight-self.height
        self.clamp_position()
        self.create_surface()
        self.last_frame=-1
        animation=self.animations[self.current]
        index=min(bisect_right(animation['endpoints'],self.elapsed%animation['duration']),len(animation['frames'])-1)
        self.draw(index)
        logging.info('Resize %s',self.scale)

    def menu(self):
        self.drag_offset=None
        user.ReleaseCapture()
        p=POINT()
        user.GetCursorPos(C.byref(p))
        menu=user.CreatePopupMenu()
        def item(command,label,checked=False):
            user.AppendMenuW(menu,0x8 if checked else 0,command,label)
        item(10,'自动轮换待机动作',self.auto)
        item(11,'站立待机',not self.auto and self.current=='standing')
        item(12,'坐着喝饮料',not self.auto and self.current=='drinking')
        item(13,'趴着读书',not self.auto and self.current=='reading')
        user.AppendMenuW(menu,0x800,0,None)
        item(20,'继续播放' if self.paused else '暂停动画')
        item(31,'小号',abs(self.scale-.7)<.01)
        item(32,'中号',abs(self.scale-1)<.01)
        item(33,'大号',abs(self.scale-1.3)<.01)
        user.AppendMenuW(menu,0x800,0,None)
        item(40,'退出桌宠')
        user.SetForegroundWindow(self.hwnd)
        command=user.TrackPopupMenu(menu,0x0100|0x0002,p.x,p.y,0,self.hwnd,None)
        user.DestroyMenu(menu)
        self.last_tick=time.perf_counter()
        if command==10:
            self.playlist_index=0
            self.switch('standing',True)
        elif command in (11,12,13):
            self.switch({11:'standing',12:'drinking',13:'reading'}[command])
        elif command==20:self.paused=not self.paused
        elif command in (31,32,33):self.resize({31:.7,32:1,33:1.3}[command])
        elif command==40:user.DestroyWindow(self.hwnd)

    def window_proc(self,hwnd,msg,wparam,lparam):
        try:
            if msg==0x0113:
                self.tick()
                return 0
            if msg==0x0201:
                p=POINT()
                user.GetCursorPos(C.byref(p))
                self.drag_offset=(p.x-self.x,p.y-self.y)
                user.SetCapture(hwnd)
                return 0
            if msg==0x0200 and self.drag_offset:
                p=POINT()
                user.GetCursorPos(C.byref(p))
                self.x=p.x-self.drag_offset[0]
                self.y=p.y-self.drag_offset[1]
                self.clamp_position()
                user.SetWindowPos(hwnd,None,self.x,self.y,0,0,0x0001|0x0004|0x0010)
                return 0
            if msg==0x0202:
                self.drag_offset=None
                user.ReleaseCapture()
                return 0
            if msg==0x0215:
                self.drag_offset=None
                return 0
            if msg==0x0205:
                self.menu()
                return 0
            if msg==0x020A:
                delta=C.c_short((wparam>>16)&0xffff).value
                self.resize(round(self.scale+(.1 if delta>0 else -.1),2))
                return 0
            if msg==0x0100:
                if wparam==27:user.DestroyWindow(hwnd)
                elif wparam==32:self.paused=not self.paused
                return 0
            if msg==0x0084 and self.hwnd:
                x=C.c_short(lparam&0xffff).value-self.x
                y=C.c_short((lparam>>16)&0xffff).value-self.y
                frame=self.animations[self.current]['frames'][self.frame_index]
                fx,fy=frame['offset']
                fw,fh=frame['size']
                if 0<=x-fx<fw and 0<=y-fy<fh and frame['alpha'][(y-fy)*fw+x-fx]>20:return 1
                return -1
            if msg==0x0010:
                user.DestroyWindow(hwnd)
                return 0
            if msg==0x0002:
                user.KillTimer(hwnd,1)
                self.free_surface()
                if not self.qa_mode:
                    try:SETTINGS.write_text(json.dumps({'x':self.x,'y':self.y,'scale':self.scale}),encoding='utf-8')
                    except OSError:pass
                logging.info('Exited cleanly')
                if self.qa_mode:
                    qa={'draws':self.draw_times,'render_ms':[x*1000 for x in self.render_times]}
                    (APP_DIR/'work'/'playback-qa.json').write_text(json.dumps(qa),encoding='utf-8')
                user.PostQuitMessage(0)
                return 0
        except Exception:
            logging.exception('Window procedure failed')
            if self.hwnd:user.DestroyWindow(hwnd)
            return 0
        return user.DefWindowProcW(hwnd,msg,wparam,lparam)

    def run(self):
        message=W.MSG()
        while True:
            while user.PeekMessageW(C.byref(message),None,0,0,1):
                if message.message==0x0012:return
                user.TranslateMessage(C.byref(message))
                user.DispatchMessageW(C.byref(message))
            self.tick()
            if not self.bits:continue
            if self.paused:
                timeout=30
            else:
                animation=self.animations[self.current]
                t=self.elapsed%animation['duration']
                index=min(bisect_right(animation['endpoints'],t),len(animation['frames'])-1)
                remaining=animation['endpoints'][index]-t
                # WM_TIMER has a 10 ms floor. Waiting for each media deadline
                # allows the 16/17 ms animation cadence without 10/20 ms beats.
                timeout=max(1,math.ceil(remaining*1000-(time.perf_counter()-self.last_tick)*1000))
            result=user.MsgWaitForMultipleObjectsEx(0,None,timeout,0x04FF,0x0004)
            if result==0xffffffff:raise C.WinError(C.get_last_error())

def main():
    try:
        try:user.SetProcessDPIAware()
        except AttributeError:pass
        mutex_name='Local\\CitlaliDesktopPet_20261014'
        if '--qa-seconds' in sys.argv:mutex_name+=f'_QA_{os.getpid()}'
        mutex=kernel.CreateMutexW(None,False,mutex_name)
        if C.get_last_error()==183:
            kernel.CloseHandle(mutex)
            return
        timer_period=winmm.timeBeginPeriod(1)==0
        try:DesktopPet().run()
        finally:
            if timer_period:winmm.timeEndPeriod(1)
            kernel.CloseHandle(mutex)
    except Exception as error:
        logging.exception('Startup failed')
        user.MessageBoxW(None,f'桌宠启动失败：{error}\n请查看程序旁的 pet.log。','茜特菈莉桌宠',0x10)
        raise

if __name__=='__main__':
    main()
