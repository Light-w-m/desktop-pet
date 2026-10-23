"""Exercise real drag messages, transparent frames and interruption recovery."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
sys.argv += ['--qa-seconds','300','--qa-assets',str(ROOT/'work'/'repaired-assets')]
from citlali_pet import app as app
from citlali_pet.animation.frame_stream import FrameArchive

folder = ROOT/'assets'/'dragging'
metadata = json.loads((folder/'source.json').read_text())
for name,expected in metadata['files'].items():
    assert hashlib.sha256((folder/name).read_bytes()).hexdigest() == expected['sha256']
archive = FrameArchive(folder/'pet-frames.json')
animation = archive.animations['dragging']
assert len(animation['frames']) == 186 and abs(animation['duration']-3.1) < 1e-8
assert {f['ms'] for f in animation['frames']} == {16,17}
for index in range(186):
    frame = archive.read('dragging',index,(560,480))
    pixels = np.frombuffer(frame['pixels'],dtype='uint8').reshape(-1,4)
    assert np.all(pixels[:,:3] <= pixels[:,3:4]), 'Transparent edge is not premultiplied'
    x,y = frame['offset'];width,height = frame['size']
    assert x >= 6 and y >= 6 and x+width <= 554 and y+height <= 474

app.PinkMenu.activate = False
app.PinkMenu.extra_style = 0x08000000
native_open = app.PinkMenu.open
def hidden_open(self,x,y):
    native_open(self,x,y)
    app.user.ShowWindow(self.hwnd,0)
app.PinkMenu.open = hidden_open
app.user.SetProcessDPIAware()
app.signature(app.user,'SendMessageW',app.LRESULT,app.W.HWND,app.W.UINT,app.WPARAM,app.LPARAM)
pet = app.DesktopPet()
app.user.ShowWindow(pet.hwnd,0)
pet.qa_report = ROOT/'work'/'menu-playback-qa.json'


def pump(seconds):
    until = time.perf_counter()+seconds
    message = app.W.MSG()
    while time.perf_counter() < until:
        while app.user.PeekMessageW(C.byref(message),None,0,0,1):
            app.user.TranslateMessage(C.byref(message))
            app.user.DispatchMessageW(C.byref(message))
        pet.tick()
        time.sleep(.003)


def mouse(message,x,y,buttons=1):
    def position(pointer):
        point = C.cast(pointer,C.POINTER(app.POINT)).contents
        point.x,point.y = x,y
        return True
    with patch.object(app.user,'GetCursorPos',side_effect=position):
        app.user.SendMessageW(pet.hwnd,message,buttons,0)
    assert pet.bits


def grab():
    x,y = pet.x+150,pet.y+150
    mouse(0x0201,x,y)
    mouse(0x0200,x+40,y+30)
    assert pet.dragging and pet.drag_motion.active


def release():
    mouse(0x0202,pet.x+150,pet.y+150,0)


try:
    pet.clock.current = pet.current = 'reading'
    pet.clock.position = pet.elapsed = 4.2
    index = app.bisect_right(pet.animations['reading']['endpoints'],4.2)
    pet.draw(index)
    before = pet.displayed_frame
    held_position = pet.clock.position
    grab()
    pump(.35)
    assert pet.drag_motion.weight == 1 and pet.visual_pose == 'dragging'
    assert pet.clock.position == held_position and pet.current == 'reading'
    assert pet.displayed_frame['pixels'] != before['pixels']
    assert pet.expression_key in ('hide','hello')
    preview = Image.new('RGBA',(pet.width,pet.height),'#eadfe7')
    preview.alpha_composite(Image.frombytes('RGBA',(pet.width,pet.height),
        C.string_at(pet.bits,pet.width*pet.height*4),'raw','BGRA'))
    preview.convert('RGB').save(ROOT/'work'/'dragging-native.jpg')
    elapsed = pet.drag_motion.elapsed
    release()
    pump(.065)
    assert 0 < pet.drag_motion.weight < 1 and pet.clock.position == held_position
    weight = pet.drag_motion.weight
    grab()
    assert pet.drag_motion.weight == weight and pet.drag_motion.elapsed >= elapsed
    pump(.15)
    assert pet.drag_motion.weight == 1
    pet.resize(.7)
    assert pet.drag_motion.visible and pet.current == 'reading'
    pet.resize(1)
    release()
    pump(.3)
    assert not pet.drag_motion.visible and pet.drag_motion.held_frame is None
    assert pet.current == 'reading' and held_position < pet.clock.position < held_position+.3
    pet.paused = True
    held_position = pet.clock.position
    grab()
    pump(.25)
    assert pet.drag_motion.elapsed > .2 and pet.clock.position == held_position
    app.user.SendMessageW(pet.hwnd,0x0215,0,0)
    pump(.25)
    assert not pet.drag_motion.visible and pet.paused and pet.clock.position == held_position
    assert pet.stream.peak_cache_frames <= 12 and pet.stream.peak_cache_bytes <= 24*1024**2
    try:
        pet.stream.get('dragging',200,(560,480))
        raise AssertionError('Invalid frame request was accepted')
    except IndexError:
        pass
    assert app.user.SendMessageW(pet.hwnd,0x0084,0,(pet.x | (pet.y << 16))) == -1
    report = {'all_186_frames_and_checksums':True,'transparent_premultiplied_edges_and_margins':True,
              'native_drag_starts_gif':True,'previous_action_phase_held_and_resumed':True,
              'release_crossfade_and_fast_regrab':True,'resize_during_drag':True,
              'drag_animation_while_main_paused':True,'capture_loss_fades_back':True,
              'interaction_expression_preserved':True,'single_bounded_frame_cache':True}
    (ROOT/'work'/'dragging-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
finally:
    app.user.DestroyWindow(pet.hwnd)
