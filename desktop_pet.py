"""A local Windows desktop pet with per-pixel transparency and original frames."""
from __future__ import annotations

import ctypes as C
import copy
from ctypes import wintypes as W
from bisect import bisect_right
import json
import logging
import math
import os
from pathlib import Path
import random
import sys
import time
from frame_stream import FrameArchive, FrameStream
from expressions import ExpressionBadge, ExpressionPicker, StickerLibrary
from pet_menu import PinkMenu, monitor_work_area
from playback import Playback
from voice_library import VoiceLibrary
from voices import VoicePicker, VoicePlayer
from voice_actions import VoiceActions
from drag_motion import DragMotion
from shake_motion import ShakeDetector, StompMotion
from pixel_surface import PixelSurface
from walking import WalkingMotion, WalkingSpeech

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
signature(user, 'SetForegroundWindow', W.BOOL, W.HWND)
signature(user, 'PostQuitMessage', None, C.c_int)
signature(user, 'MessageBoxW', C.c_int, W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT)
signature(user, 'LoadCursorW', W.HANDLE, W.HINSTANCE, C.c_void_p)
signature(user, 'LoadImageW', W.HANDLE, W.HINSTANCE, W.LPCWSTR, W.UINT, C.c_int, C.c_int, W.UINT)
signature(user, 'UpdateLayeredWindow', W.BOOL, W.HWND, W.HDC, C.POINTER(POINT), C.POINTER(SIZE), W.HDC, C.POINTER(POINT), W.DWORD, C.POINTER(BLEND), W.DWORD)
signature(gdi, 'CreateCompatibleDC', W.HDC, W.HDC)
signature(gdi, 'CreateDIBSection', W.HANDLE, W.HDC, C.POINTER(BITMAPINFO), W.UINT, C.POINTER(C.c_void_p), W.HANDLE, W.DWORD)
signature(gdi, 'SelectObject', W.HANDLE, W.HDC, W.HANDLE)
signature(gdi, 'DeleteObject', W.BOOL, W.HANDLE)
signature(gdi, 'DeleteDC', W.BOOL, W.HDC)

class DesktopPet:
    LABELS = {'standing': '站立待机', 'drinking': '坐着喝饮料', 'reading': '趴着读书'}
    INTERACTION_EXPRESSIONS = {'double_click':('annoyed','blush'),'drag':('hide','hello')}

    def __init__(self):
        self.settings = {}
        try:
            self.settings = json.loads(SETTINGS.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        self.scale = float(self.settings.get('scale', 1.0))
        if '--qa-seconds' in sys.argv and '--qa-scale' in sys.argv:
            self.scale = float(sys.argv[sys.argv.index('--qa-scale')+1])
        self.scale = max(.6, min(1.5, self.scale))
        self.auto = False
        self.paused = False
        self.drag_motion = DragMotion()
        self.stomp_motion = StompMotion()
        self.walking = WalkingMotion()
        self.walking_speech = WalkingSpeech()
        self.walking_states = []
        self.shake = ShakeDetector()
        self.last_stomp_time = float('-inf')
        self.reset_drag()
        self.interaction_random = random.Random()
        self.current = 'standing'
        self.last_frame = -1
        self.last_drag_frame = None
        self.last_stomp_frame = None
        self.last_walk_frame = None
        self.draw_times = []
        self.render_times = []
        self.reaction_states = []
        self.frame_index = 0
        self.elapsed = 0.0
        self.last_tick = time.perf_counter()
        self.started = self.last_tick
        self.qa_seconds = float(sys.argv[sys.argv.index('--qa-seconds') + 1]) if '--qa-seconds' in sys.argv else 0
        self.qa_mode = '--qa-seconds' in sys.argv
        self.qa_drag = '--qa-drag' in sys.argv
        self.qa_stomp = '--qa-stomp' in sys.argv
        self.qa_walk = '--qa-walk' in sys.argv
        self.qa_report = APP_DIR/'work'/('walk-playback-qa.json' if self.qa_walk else 'stomp-playback-qa.json' if self.qa_stomp else
                                       'drag-playback-qa.json' if self.qa_drag else 'playback-qa.json')
        self.animations = {}
        self.popup = None
        self.expression = None
        self.expression_key = None
        self.expression_expires_at = None
        self.stickers = StickerLibrary(APP_DIR/'assets'/'expressions', RESOURCE_DIR/'assets'/'expressions')
        self.voices = VoiceLibrary(APP_DIR,RESOURCE_DIR)
        try:
            voice_volume = int(self.settings.get('voice_volume',100))
        except (TypeError,ValueError):
            voice_volume = 100
        self.voice_player = VoicePlayer(volume=voice_volume,muted=self.settings.get('voice_muted',False))
        self.voice_actions = VoiceActions()
        self.voice_manual = False
        self.voice_reaction = False
        self.displayed_frame = None
        self.hwnd = None
        self.dc = self.bitmap = self.old_bitmap = self.bits = None
        self.surface = None
        self.blend = BLEND(0, 0, 255, 1)
        self.load_frames()
        self.clock=Playback({name:animation['duration'] for name,animation in self.animations.items()})
        self.qa_target=None
        work = W.RECT()
        if not user.SystemParametersInfoW(0x0030, 0, C.byref(work), 0):
            raise C.WinError(C.get_last_error())
        self.x = int(self.settings.get('x', work.right - self.width - 35))
        self.y = int(self.settings.get('y', work.bottom - self.height))
        if 'y' in self.settings:
            # Preserve the bottom anchor when upgrading the old 420px canvas
            # or when the saved scale/canvas dimensions change.
            saved_height=int(self.settings.get('height',round(420*self.scale)))
            self.y+=saved_height-self.height
        self.clamp_position()
        self.callback = WNDPROC(self.window_proc)
        self.instance = kernel.GetModuleHandleW(None)
        classname = 'CitlaliDesktopPetWindow_20261014'
        wc = WNDCLASS()
        wc.style = 0x0008  # CS_DBLCLKS: let Windows recognize the user's double-click timing.
        wc.lpfnWndProc = self.callback
        wc.hInstance = self.instance
        icon_file=APP_DIR/'assets/app.ico'
        if not icon_file.is_file():icon_file=RESOURCE_DIR/'assets/app.ico'
        if icon_file.is_file():
            wc.hIcon=user.LoadImageW(None,str(icon_file),1,0,0,0x10 | 0x40)
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
        logging.info('Started. hwnd=%s size=%sx%s frames=%s bounded streaming cache', self.hwnd, self.width, self.height, {k:len(v['frames']) for k,v in self.animations.items()})

    def load_frames(self):
        manifest = json.loads((ASSETS / 'manifest.json').read_text(encoding='utf-8'))
        self.width, self.height = [round(x*self.scale) for x in manifest.get('display_canvas',manifest['canvas'])]
        if not self.animations:
            archive_path=ASSETS/manifest['playback_pack']
            if not archive_path.is_file():
                # Ship the pack inside the standalone EXE without keeping a
                # second copy beside it. Source runs reuse the build output.
                folder=RESOURCE_DIR/'assets' if getattr(sys,'frozen',False) else APP_DIR/'work'/'repaired-assets'
                archive_path=folder/manifest['playback_pack']
            archive = FrameArchive(archive_path)
            for name in ('dragging', 'stomping', 'walking'):
                if name in archive.animations or (name == 'walking' and 'walking_left' in archive.animations):
                    continue
                for folder in (APP_DIR/'assets',RESOURCE_DIR/'assets',ASSETS):
                    optional = folder/name/'pet-frames.json'
                    if optional.is_file():
                        archive.include(optional)
                        break
            self.animations = archive.animations
            # Stable upper-right pose bounds in default display coordinates.
            sx, sy = (d/n for d, n in zip(archive.display_canvas, archive.canvas))
            self.pose_bounds = {
                name: (min(f['native'][2] for f in animation['frames'])*sx,
                       min(f['native'][3] for f in animation['frames'])*sy,
                       max(f['native'][4] for f in animation['frames'])*sx,
                       max(f['native'][5] for f in animation['frames'])*sy)
                for name, animation in self.animations.items()}
            self.expression_anchors = {name:(bounds[2],bounds[1]) for name,bounds in self.pose_bounds.items()}
            self.stream = FrameStream(archive)
        else:
            self.stream.clear()

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
        self.surface=PixelSurface(self.bits.value,(self.width,self.height))

    def free_surface(self):
        if self.surface:
            self.surface.close()
            self.surface=None
        if self.dc:
            if self.old_bitmap:gdi.SelectObject(self.dc,self.old_bitmap)
            if self.bitmap:gdi.DeleteObject(self.bitmap)
            gdi.DeleteDC(self.dc)
        self.dc=self.bitmap=self.old_bitmap=self.bits=None

    def draw(self,index):
        render_start=time.perf_counter()
        self.frame_index=index
        size=self.width,self.height
        render_name,render_index=self.current,index
        if self.walking.visible:
            walk = self.walking
            if walk.preparing:
                frame = self.displayed_frame
            else:
                animation = self.animations[walk.name]
                phase=min(walk.elapsed,animation['duration']) if walk.turning else walk.elapsed % animation['duration']
                render_index = min(bisect_right(animation['endpoints'],phase),len(animation['frames'])-1)
                render_name = walk.name
                base = self.stream.get(self.current,index,size) if not walk.active else walk.entry_frame
                frame = walk.blend(self.stream.get(walk.name,render_index,size),size,base)
        elif self.stomp_motion.visible and not self.stomp_motion.preparing:
            base = self.stream.get(self.current,index,size) if self.stomp_motion.held_frame is None else None
            if base is not None:
                self.stomp_motion.held_frame = self.stomp_motion.entry_frame = base
            animation = self.animations['stomping']
            render_index = min(bisect_right(animation['endpoints'],self.stomp_motion.elapsed),len(animation['frames'])-1)
            render_name = 'stomping'
            base = None
            if self.stomp_motion.elapsed < self.stomp_motion.FADE_IN and self.drag_motion.visible:
                drag_index = self.drag_index()
                outgoing = self.stream.peek('dragging',drag_index,size)
                if outgoing is not None:
                    base = self.drag_motion.blend(outgoing,size)
            elif self.stomp_motion.elapsed > animation['duration']-self.stomp_motion.FADE_OUT:
                base = self.stream.peek(self.current,index,size)
            frame = self.stomp_motion.blend(self.stream.get('stomping',render_index,size),size,base)
        elif self.stomp_motion.preparing and not self.drag_motion.visible:
            frame=self.displayed_frame
        elif self.drag_motion.visible and 'dragging' in self.animations:
            if self.drag_motion.held_frame is None:
                self.drag_motion.held_frame=self.stream.get(self.current,index,size)
                self.drag_motion.entry_frame=self.drag_motion.held_frame
            animation=self.animations['dragging']
            phase=self.drag_motion.elapsed%animation['duration']
            render_index=min(bisect_right(animation['endpoints'],phase),len(animation['frames'])-1)
            render_name='dragging'
            frame=self.drag_motion.blend(self.stream.get('dragging',render_index,size),size)
        else:
            self.drag_motion.clear()
            self.stomp_motion.clear()
            frame=self.stream.get(self.current,index,size)
        self.displayed_frame=frame
        self.surface.paint(frame)
        pt=POINT(self.x,self.y)
        src=POINT(0,0)
        size=SIZE(self.width,self.height)
        if not user.UpdateLayeredWindow(self.hwnd,None,C.byref(pt),C.byref(size),self.dc,C.byref(src),0,C.byref(self.blend),2):
            raise C.WinError(C.get_last_error())
        self.last_frame=index
        self.last_drag_frame=render_index if render_name == 'dragging' else None
        self.last_stomp_frame=render_index if render_name == 'stomping' else None
        self.last_walk_frame=(render_name,render_index) if render_name.startswith('walking_') else None
        if self.expression:self.expression.follow()
        if self.popup:self.popup.follow()
        if self.qa_mode:
            completed=time.perf_counter()
            self.draw_times.append((render_name,render_index,completed))
            self.render_times.append(completed-render_start)
            if self.qa_stomp:
                self.reaction_states.append({'pose':render_name,'time':completed,
                    'weight':self.stomp_motion.weight,'elapsed':self.stomp_motion.elapsed,
                    'main_pose':self.current,'main_position':self.clock.position})

    def switch(self,name,automatic=False):
        if self.walking.visible:
            self.stop_walking()
            self.clock.current = self.current = name
            self.clock.position = self.elapsed = 0.0
        self.clock.request(name,automatic)
        self.auto=automatic
        self.last_tick=time.perf_counter()
        logging.info('Requested %s auto=%s current=%s pending=%s',name,automatic,self.current,self.clock.pending)

    def tick(self):
        now=time.perf_counter()
        dt=max(0,now-self.last_tick)
        self.last_tick=now
        if self.qa_seconds and now-self.started>=self.qa_seconds:
            user.DestroyWindow(self.hwnd)
            return
        if self.qa_walk:
            age = now-self.started
            if age >= .5 and self.qa_target is None:
                self.qa_target = 'walking'
                self.start_walking()
                self.walking.left,self.walking.right = self.x-80,self.x+80
            if age >= self.qa_seconds-1 and self.qa_target == 'walking':
                self.qa_target = 'stopped'
                self.stop_walking()
        elif self.qa_stomp:
            if now-self.started >= .6 and self.qa_target is None:
                self.qa_target = 'dragging'
                self.start_drag_animation()
            if now-self.started >= 1.2 and self.qa_target == 'dragging':
                self.qa_target = 'stomping'
                self.start_stomp(now)
        elif self.qa_drag:
            active=1.5 <= now-self.started < self.qa_seconds-1.5
            if active != self.drag_motion.active:
                if active:self.start_drag_animation()
                else:self.drag_motion.stop()
        elif self.qa_mode:
            names=['standing','drinking','reading']
            name=names[min(2,int((now-self.started)/max(3,self.qa_seconds/3)))]
            if self.qa_target!=name:
                self.qa_target=name
                self.switch(name,False)
        if self.expression_expires_at is not None and now>=self.expression_expires_at:
            self.show_expression(None)
        self.voice_player.poll()
        if self.popup:self.popup.refresh()
        if self.walking.visible:
            self.tick_walking(dt)
            return
        if self.dragging and self.shake.idle(now):
            self.try_stomp(now)
        was_dragging=self.drag_motion.visible
        was_stomping=self.stomp_motion.visible
        was_interacting=was_dragging or was_stomping
        stomp=self.stomp_motion
        if stomp.visible:
            if stomp.elapsed < stomp.FADE_IN and self.drag_motion.visible:
                self.drag_motion.active=True
            if stomp.preparing:
                keys=self.warm_stomp()
                if all(self.stream.peek(*key) is not None for key in keys):
                    self.stream.request('stomping',0,(self.width,self.height))
                    stomp.held_frame=self.stream.peek('standing',0,(self.width,self.height))
                    stomp.preparing=False
                    # Start the media clock after decoding/preparation. A slow
                    # disk must not skip the first part of the crossfade.
                    self.last_tick=time.perf_counter()
                    dt=0
                    self.play_stomp_voice()
            if not stomp.preparing:
                if stomp.elapsed < stomp.FADE_IN and self.drag_motion.visible:
                    self.drag_motion.active=True
                    self.stream.prefetch(self.drag_keys(self.drag_motion.elapsed+dt))
                elif stomp.elapsed >= stomp.duration-stomp.FADE_OUT-stomp.RETURN_PRELOAD:
                    keys=self.return_keys(dt)
                    self.stream.prefetch(keys)
                    base=self.stream.peek(*keys[0])
                    if base is not None:
                        self.stomp_motion.held_frame=base
                else:
                    # Let the short reaction's lookahead fill after its entry
                    # fade before decoding the return animation. Its neutral
                    # standing frame is already held from initial preparation.
                    self.stream.prefetch()
        self.drag_motion.advance(dt)
        before_return=max(0,stomp.elapsed-stomp.duration+stomp.FADE_OUT) if was_stomping else 0
        self.stomp_motion.advance(dt)
        if was_stomping and not stomp.preparing:
            returned=max(0,stomp.elapsed-stomp.duration+stomp.FADE_OUT)-before_return
            if returned > 0 and not self.paused:
                self.clock.advance(returned)
            if stomp.elapsed >= stomp.FADE_IN:
                self.drag_motion.clear()
        interacting=self.drag_motion.visible or self.stomp_motion.visible
        if self.paused and not (was_interacting or interacting):return
        previous=self.current
        if not self.paused and not (was_interacting or interacting):
            self.clock.advance(dt)
        self.current=self.clock.current
        self.elapsed=self.clock.position
        if self.current!=previous:
            self.last_frame=-1
            logging.info('Animation %s after native return from %s',self.current,previous)
        if not self.qa_mode and not interacting and not self.paused:
            self.update_automatic_voice(dt)
        animation=self.animations[self.current]
        t=self.elapsed%animation['duration']
        index=min(bisect_right(animation['endpoints'],t),len(animation['frames'])-1)
        drag_changed=False
        if self.drag_motion.visible:
            drag=self.animations['dragging']
            phase=self.drag_motion.elapsed%drag['duration']
            drag_index=min(bisect_right(drag['endpoints'],phase),len(drag['frames'])-1)
            drag_changed=drag_index!=self.last_drag_frame or 0 < self.drag_motion.weight < 1
        stomp_changed=False
        if self.stomp_motion.visible:
            stomp=self.animations['stomping']
            stomp_index=min(bisect_right(stomp['endpoints'],self.stomp_motion.elapsed),len(stomp['frames'])-1)
            stomp_changed=stomp_index!=self.last_stomp_frame or 0 < self.stomp_motion.weight < 1
        if index!=self.last_frame or drag_changed or stomp_changed or (was_interacting and not interacting):self.draw(index)
        if was_stomping and not interacting:
            self.stream.prefetch()

    def start_walking(self):
        if not all(name in self.animations for name in ('walking_left','walking_right')):
            return False
        self.reset_drag()
        self.drag_motion.clear()
        self.stomp_motion.clear()
        self.clock.current = self.current = 'standing'
        self.clock.position = self.elapsed = self.clock.stage_elapsed = 0.0
        self.clock.pending = None
        self.clock.playlist_index = 0
        self.clock.cycle += 1
        self.clock.automatic = self.auto = self.paused = False
        self.voice_actions.defer(cancel_drinking=True)
        self.walking_speech.restart()
        bounds = [bounds for name,bounds in self.pose_bounds.items() if name.startswith('walking_')]
        left = min(b[0] for b in bounds)*self.scale
        right = max(b[2] for b in bounds)*self.scale
        area = monitor_work_area(sys.modules[__name__],round(self.x+(left+right)/2),self.y+self.height//2)
        limits = area.left-left+2,area.right-right-2
        if limits[1] < limits[0]:
            return False
        self.walking.start(self.x,self.y,limits,self.scale,self.displayed_frame)
        self.walking.turn_duration=self.animations.get('walking_turn',{}).get('duration',0)
        self.stream.prefetch([(self.walking.name,i,(self.width,self.height)) for i in range(3)])
        self.last_tick = time.perf_counter()
        return True

    def stop_walking(self):
        if not self.walking.visible:return
        self.walking.stop()
        if self.walking_speech.owns(self.voice_player.current_id):
            self.voice_player.stop()
        self.walking_speech.restart()
        self.voice_actions.defer(cancel_drinking=True)
        self.stream.prefetch([('standing',i,(self.width,self.height)) for i in range(3)])

    def tick_walking(self, dt):
        walk = self.walking
        old_position = self.x,self.y
        size = self.width,self.height
        if walk.preparing:
            keys = [(walk.name,i,size) for i in range(3)]
            self.stream.prefetch(keys)
            if not all(self.stream.peek(*key) is not None for key in keys):return
            self.stream.request(walk.name,0,size)
            walk.preparing = False
            self.last_tick = time.perf_counter()
            dt = 0
        if walk.active:
            other = 'walking_right' if walk.direction < 0 else 'walking_left'
            edge_distance = walk.x-walk.left if walk.direction < 0 else walk.right-walk.x
            if walk.turning:
                other='walking_right' if walk.direction>0 else 'walking_left'
                self.stream.prefetch([(other,i,size) for i in range(3)])
            elif edge_distance < walk.speed*.5:
                if walk.turn_duration>0:other='walking_turn' if walk.direction<0 else 'walking_turn_back'
                self.stream.prefetch([(other,i,size) for i in range(3)])
            else:
                self.stream.prefetch()
        walk.advance(dt)
        if walk.active:
            self.x,self.y = round(walk.x),walk.y
            if not self.qa_mode:
                player = self.voice_player
                title = self.walking_speech.advance(dt,player.current_id,{r['title'] for r in self.voices.records},
                    enabled=not player.muted and player.volume > 0,busy=isinstance(self.popup,VoicePicker))
                if title:
                    record = next(r for r in self.voices.records if r['title'] == title)
                    if self.play_voice(record['id'],automatic=True):self.walking_speech.started(record['id'])
                    else:self.walking_speech.defer()
        elif not self.paused:
            self.clock.advance(dt)
            self.elapsed = self.clock.position
        animation = self.animations[self.current]
        index = min(bisect_right(animation['endpoints'],self.clock.position),len(animation['frames'])-1)
        animation = self.animations[walk.name]
        phase=min(walk.elapsed,animation['duration']) if walk.turning else walk.elapsed % animation['duration']
        walking_index = min(bisect_right(animation['endpoints'],phase),len(animation['frames'])-1)
        changing_blend = 0 < walk.weight < 1 or walk.turn_elapsed < walk.TURN
        if not walk.visible or changing_blend or self.last_walk_frame != (walk.name,walking_index):
            self.draw(index)
        elif old_position != (self.x,self.y):
            # An input/message can wake us before the next media deadline.
            # Move the existing surface without decoding or repainting it.
            user.SetWindowPos(self.hwnd,None,self.x,self.y,0,0,0x0001|0x0004|0x0010)
            if self.expression:self.expression.follow()
        if self.qa_mode:
            self.walking_states.append({'x':self.x,'y':self.y,'direction':walk.direction,'active':walk.active,
                'left':walk.left,'right':walk.right,'time':time.perf_counter()})
        if not walk.visible:
            walk.clear()
            self.last_frame = -1
            self.stream.prefetch()

    def warm_stomp(self):
        if 'stomping' not in self.animations:
            return []
        keys=[('stomping',i,(self.width,self.height)) for i in range(2)]
        keys.append(('standing',0,(self.width,self.height)))
        self.stream.prefetch(keys)
        return keys

    def drag_index(self):
        animation=self.animations['dragging']
        return min(bisect_right(animation['endpoints'],self.drag_motion.elapsed % animation['duration']),
                   len(animation['frames'])-1)

    def drag_keys(self, position):
        animation=self.animations['dragging']
        start=bisect_right(animation['endpoints'],position % animation['duration'])
        return [('dragging',(start+i) % len(animation['frames']),(self.width,self.height)) for i in range(3)]

    def return_keys(self, seconds):
        stomp=self.stomp_motion
        threshold=stomp.duration-stomp.FADE_OUT
        returned=max(0,min(stomp.duration,stomp.elapsed+seconds)-threshold)-max(0,stomp.elapsed-threshold)
        clock=copy.copy(self.clock)
        if not self.paused:
            clock.advance(returned)
        keys=[]
        for _ in range(3):
            animation=self.animations[clock.current]
            index=min(bisect_right(animation['endpoints'],clock.position),len(animation['frames'])-1)
            keys.append((clock.current,index,(self.width,self.height)))
            if not self.paused:
                clock.advance(1/60)
        return keys

    def clamp_position(self):
        left=user.GetSystemMetrics(76)
        top=user.GetSystemMetrics(77)
        right=left+user.GetSystemMetrics(78)
        bottom=top+user.GetSystemMetrics(79)
        self.x=max(left,min(self.x,right-self.width))
        self.y=max(top,min(self.y,bottom-self.height))

    def resize(self,scale):
        self.stop_walking()
        self.walking.clear()
        oldwidth,oldheight=self.width,self.height
        self.scale=max(.6,min(1.5,scale))
        self.load_frames()
        self.drag_motion.held_frame=None
        self.drag_motion.entry_frame=None
        self.stomp_motion.held_frame=self.stomp_motion.entry_frame=None
        self.x+=(oldwidth-self.width)//2
        self.y+=oldheight-self.height
        self.clamp_position()
        self.create_surface()
        self.last_frame=-1
        animation=self.animations[self.current]
        index=min(bisect_right(animation['endpoints'],self.elapsed%animation['duration']),len(animation['frames'])-1)
        self.draw(index)
        if self.expression_key:self.show_expression(self.expression_key,reset_timer=False)
        # Decoding resized frames takes real time; it must not advance media.
        self.last_tick=time.perf_counter()
        logging.info('Resize %s',self.scale)

    def popup_bounds(self,name=None):
        left,top,right,bottom=self.pose_bounds[name or self.visual_pose]
        return (self.x+math.floor(left*self.scale),self.y+math.floor(top*self.scale),
                self.x+math.ceil(right*self.scale),self.y+math.ceil(bottom*self.scale))

    def menu(self, position=None, picker=False, voices=False):
        self.stop_walking()
        self.reset_drag()
        user.ReleaseCapture()
        p=POINT()
        user.GetCursorPos(C.byref(p))
        if self.popup:self.popup.close()
        if position:p.x,p.y=position
        menu_type=VoicePicker if voices else ExpressionPicker if picker else PinkMenu
        self.popup=menu_type(self,sys.modules[__name__])
        self.popup.open(p.x,p.y)

    def reset_drag(self):
        self.drag_offset = self.drag_origin = None
        self.dragging = False
        self.drag_motion.stop()
        self.shake.cancel()

    @property
    def visual_pose(self):
        if self.walking.visible and not self.walking.preparing:
            return self.walking.name
        if self.stomp_motion.visible:
            return 'stomping'
        return 'dragging' if self.drag_motion.visible and 'dragging' in self.animations else self.current

    def start_drag_animation(self):
        if self.walking.visible:
            self.stop_walking()
            self.walking.clear()
        if 'dragging' in self.animations:
            if self.stomp_motion.visible:
                base = self.stomp_motion.held_frame
                self.stomp_motion.clear()
                self.drag_motion.clear()
                self.drag_motion.start(self.displayed_frame,base)
            else:
                self.drag_motion.start(self.displayed_frame)
            self.warm_stomp()
            self.last_frame=-1

    def try_stomp(self, now):
        if not self.shake.consume(now) or now-self.last_stomp_time < 2.5:
            return False
        return self.start_stomp(now)

    def start_stomp(self, now):
        self.stop_walking()
        if 'stomping' not in self.animations:
            return False
        try:
            self.stickers.path('shake_angry')
        except FileNotFoundError:
            logging.warning('Hidden shake sticker is unavailable; skipping reaction')
            return False
        base = self.drag_motion.held_frame or self.displayed_frame
        self.stomp_motion.start_once(self.displayed_frame,base,self.animations['stomping']['duration'])
        # This reaction includes its own standing recovery. Start the main
        # standing clock at the shared neutral pose, preserving auto/manual
        # playback and pause preferences while cancelling the previous pose.
        self.clock.current = self.current = 'standing'
        self.clock.position = self.elapsed = 0.0
        self.clock.stage_elapsed = 0.0
        self.clock.playlist_index = 0
        self.clock.pending = None
        self.warm_stomp()
        self.last_stomp_time = now
        self.last_stomp_frame = None
        self.last_frame = -1
        self.show_expression('shake_angry')
        logging.info('Shake easter egg: stomp, then normal standing')
        return True

    def play_stomp_voice(self):
        if self.qa_mode:
            return
        player=self.voice_player
        title=self.voice_actions.stomp({r['title'] for r in self.voices.records},
                enabled=not player.muted and player.volume > 0,
                busy=player.current_id is not None and self.voice_manual)
        if title:
            record=next(r for r in self.voices.records if r['title'] == title)
            if self.play_voice(record['id'],automatic=True):
                self.voice_reaction=True

    def show_interaction_expression(self,interaction):
        self.show_expression(self.interaction_random.choice(self.INTERACTION_EXPRESSIONS[interaction]))

    def show_expression(self,key,*,reset_timer=True):
        if key is not None:self.stickers.path(key)
        if self.expression:
            self.expression.close()
            self.expression=None
        self.expression_key=key
        if key is not None:
            self.expression=ExpressionBadge(self,sys.modules[__name__],key)
            self.expression.open(self.x,self.y)
            self.expression.follow()
            if reset_timer or self.expression_expires_at is None:
                self.expression_expires_at=time.perf_counter()+5.0
        else:
            self.expression_expires_at=None
        logging.info('Expression %s',key)

    def update_automatic_voice(self,seconds):
        player = self.voice_player
        busy = player.current_id is not None
        if self.current == 'drinking':
            busy = busy and (self.voice_manual or self.voice_reaction)
        else:
            busy = busy or isinstance(self.popup,VoicePicker)
        title = self.voice_actions.advance(seconds,self.current,self.clock.cycle,
                                           position=self.clock.position,
                                           enabled=not player.muted and player.volume > 0,
                                           busy=busy,paused=self.paused,automatic=self.clock.automatic)
        if title:
            record = next((r for r in self.voices.records if r['title'] == title),None)
            if record:
                self.play_voice(record['id'],automatic=True)

    def play_voice(self,identifier,*,automatic=False):
        if not automatic:self.walking_speech.defer()
        try:
            played=self.voice_player.play(self.voices.get(identifier))
            if played:
                self.voice_manual = not automatic
                self.voice_reaction = False
                if not automatic:
                    self.voice_actions.defer(cancel_drinking=True)
            return played
        except (FileNotFoundError,StopIteration):
            if not automatic:
                self.voice_player.stop()
            self.voices.refresh()
            logging.info('Selected voice is no longer available: %s',identifier)
            return False

    def stop_voice(self):
        self.voice_player.stop()
        self.walking_speech.defer()
        self.voice_actions.defer(cancel_drinking=True)

    def configure_voice(self,*,volume=None,muted=None):
        self.voice_player.configure(volume=volume,muted=muted)
        self.voice_actions.defer(cancel_drinking=self.voice_player.muted or self.voice_player.volume == 0)
        if self.voice_player.muted or self.voice_player.volume == 0:self.walking_speech.defer()
        self.save_settings()

    def save_settings(self):
        if self.qa_mode:
            return
        self.settings.update(x=self.x,y=self.y,scale=self.scale,height=self.height,
                             voice_volume=self.voice_player.volume,voice_muted=self.voice_player.muted)
        try:
            SETTINGS.write_text(json.dumps(self.settings,ensure_ascii=False),encoding='utf-8')
        except OSError:
            logging.warning('Could not save pet preferences',exc_info=True)

    def menu_command(self,command,position=None):
        if command==10:
            self.switch('standing',True)
        elif command in (11,12,13):
            self.switch({11:'standing',12:'drinking',13:'reading'}[command])
        elif command==14:self.start_walking()
        elif command==20:
            self.stop_walking()
            self.paused=not self.paused
        elif command in (31,32,33):self.resize({31:.7,32:1,33:1.3}[command])
        elif command==40:user.DestroyWindow(self.hwnd)
        elif command==50:self.menu(position=position,picker=True)
        elif command==60:self.menu(position=position,voices=True)

    def window_proc(self,hwnd,msg,wparam,lparam):
        try:
            if self.popup and hwnd==self.popup.hwnd:
                return self.popup.window_proc(hwnd,msg,wparam,lparam)
            if self.expression and hwnd==self.expression.hwnd:
                return self.expression.window_proc(hwnd,msg,wparam,lparam)
            if msg==0x0047 and hwnd==self.hwnd and self.expression:
                self.expression.follow()
            if msg==0x0113:
                self.tick()
                return 0
            if msg in (0x0201,0x0203):
                self.stop_walking()
                p=POINT()
                user.GetCursorPos(C.byref(p))
                self.drag_offset=(p.x-self.x,p.y-self.y)
                self.drag_origin=(p.x,p.y)
                self.dragging=False
                self.shake.begin(p.x,p.y,time.perf_counter(),self.scale)
                user.SetCapture(hwnd)
                if msg==0x0203:
                    self.show_interaction_expression('double_click')
                return 0
            if msg==0x0200 and self.drag_offset:
                if not wparam & 1:
                    self.reset_drag()
                    user.ReleaseCapture()
                    return 0
                p=POINT()
                user.GetCursorPos(C.byref(p))
                if not self.dragging:
                    dx,dy=p.x-self.drag_origin[0],p.y-self.drag_origin[1]
                    if abs(dx)<max(4,abs(user.GetSystemMetrics(68))) and abs(dy)<max(4,abs(user.GetSystemMetrics(69))):
                        return 0
                old_position=self.x,self.y
                self.x=p.x-self.drag_offset[0]
                self.y=p.y-self.drag_offset[1]
                self.clamp_position()
                if (self.x,self.y)==old_position:
                    return 0
                user.SetWindowPos(hwnd,None,self.x,self.y,0,0,0x0001|0x0004|0x0010)
                first_drag = not self.dragging
                self.dragging=True
                self.shake.record(p.x,p.y,time.perf_counter())
                if self.stomp_motion.visible or not self.drag_motion.active:
                    self.start_drag_animation()
                if first_drag:
                    self.show_interaction_expression('drag')
                if self.expression:self.expression.follow()
                return 0
            if msg==0x0202:
                if self.dragging:
                    self.try_stomp(time.perf_counter())
                self.reset_drag()
                user.ReleaseCapture()
                return 0
            if msg==0x0215:
                self.reset_drag()
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
                elif wparam==32:
                    self.stop_walking()
                    self.paused=not self.paused
                return 0
            if msg==0x007E:  # Display topology changed: stop before using old bounds.
                self.stop_walking()
                return 0
            if msg==0x0084 and self.hwnd:
                x=C.c_short(lparam&0xffff).value-self.x
                y=C.c_short((lparam>>16)&0xffff).value-self.y
                frame=self.displayed_frame
                if frame is None:return -1
                fx,fy=frame['offset']
                fw,fh=frame['size']
                if 0<=x-fx<fw and 0<=y-fy<fh and frame['pixels'][((y-fy)*fw+x-fx)*4+3]>20:return 1
                return -1
            if msg==0x0010:
                user.DestroyWindow(hwnd)
                return 0
            if msg==0x0002:
                user.KillTimer(hwnd,1)
                if self.popup:self.popup.close()
                if self.expression:
                    self.expression.close()
                    self.expression=None
                self.voice_player.close()
                self.stream.close()
                self.free_surface()
                self.save_settings()
                logging.info('Exited cleanly')
                if self.qa_mode:
                    qa={'draws':self.draw_times,'render_ms':[x*1000 for x in self.render_times],
                        'peak_cache_bytes':self.stream.peak_cache_bytes,'peak_cache_frames':self.stream.peak_cache_frames,
                        'native_cache_peak_bytes':self.stream.archive.peak_raw_cache_bytes,
                        'loop_cache_peak_bytes':self.stream.archive.loop_cache.peak_bytes,
                        'walking_states':self.walking_states,
                        'reaction_states':self.reaction_states}
                    self.qa_report.parent.mkdir(exist_ok=True)
                    self.qa_report.write_text(json.dumps(qa),encoding='utf-8')
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
            if self.walking.visible:
                animation=self.animations[self.walking.name]
                phase=min(self.walking.elapsed,animation['duration']) if self.walking.turning else self.walking.elapsed % animation['duration']
                index=min(bisect_right(animation['endpoints'],phase),len(animation['frames'])-1)
                remaining=animation['endpoints'][index]-phase
                if not self.walking.active:remaining=1/60
                timeout=5 if self.walking.preparing else max(1,math.ceil(remaining*1000-(time.perf_counter()-self.last_tick)*1000))
            elif self.stomp_motion.visible:
                animation=self.animations['stomping']
                phase=self.stomp_motion.elapsed
                index=min(bisect_right(animation['endpoints'],phase),len(animation['frames'])-1)
                remaining=animation['endpoints'][index]-phase
                timeout=max(1,math.ceil(remaining*1000-(time.perf_counter()-self.last_tick)*1000))
            elif self.drag_motion.visible:
                animation=self.animations['dragging']
                phase=self.drag_motion.elapsed%animation['duration']
                index=min(bisect_right(animation['endpoints'],phase),len(animation['frames'])-1)
                remaining=animation['endpoints'][index]-phase
                timeout=max(1,math.ceil(remaining*1000-(time.perf_counter()-self.last_tick)*1000))
            elif self.paused:
                timeout=30
            else:
                animation=self.animations[self.current]
                t=self.elapsed
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
