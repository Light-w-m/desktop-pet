"""Exercise shake rejection, real native drag messages and one-shot recovery."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
from citlali_pet.animation.shake_motion import ShakeDetector

for axis in (0, 1, 2):
    detector = ShakeDetector()
    detector.begin(200, 200, 0)
    for i in range(1, 7):
        offset = 60 if i % 2 else -60
        detector.record(200+offset if axis != 1 else 200,
                        200+offset if axis != 0 else 200, i*.08)
    assert detector.armed and not detector.idle(.6) and detector.idle(.75)
    assert detector.consume(.75) and not detector.consume(.76)
for kind in ('straight', 'tiny_jitter', 'slow'):
    detector = ShakeDetector()
    detector.begin(200, 200, 0)
    for i in range(1, 30):
        x = 200+i*10 if kind == 'straight' else 200+(-1)**i*(4 if kind == 'tiny_jitter' else 60)
        detector.record(x, 200, i*(.08 if kind != 'slow' else .5))
    assert not detector.armed, kind

sys.argv += ['--qa-seconds', '300', '--qa-stomp', '--qa-assets', str(ROOT/'work'/'repaired-assets')]
from citlali_pet import app as app
from citlali_pet.ui.expressions import EXPRESSIONS, PICKER_HITS
from citlali_pet.animation.frame_stream import FrameArchive

assert len(EXPRESSIONS) == 9 and len(PICKER_HITS) == 11
assert 'shake_angry' not in dict(EXPRESSIONS)
folder = ROOT/'assets'/'stomping'
metadata = json.loads((folder/'source.json').read_text(encoding='utf-8'))
for name, expected in metadata['files'].items():
    assert hashlib.sha256((folder/name).read_bytes()).hexdigest() == expected['sha256']
archive = FrameArchive(folder/'pet-frames.json')
count = metadata['output_frames']
duration = metadata['duration_ms']/1000
assert count == round(duration*60) and count > 60
assert len(archive.animations['stomping']['frames']) == count
assert abs(archive.animations['stomping']['duration']-duration) < 1e-8
assert metadata['sequence'] == ['stomp','settle_to_standing']
assert metadata['discarded_intro_frames'] == 63 and metadata['source_range_seconds'][0] >= 1.1
assert metadata['source_range_seconds'][1] >= 6.0 and duration >= 4.9, 'Original recovery was truncated'
assert metadata['recovery']['source_ending_retained']
assert metadata['recovery']['handoff_source_seconds'][0] > metadata['recovery']['complete_source_seconds']+1
for index in range(count):
    frame = archive.read('stomping', index, (560, 480))
    assert all(frame['pixels'][i] <= frame['pixels'][i-i % 4+3]
               for i in range(len(frame['pixels'])) if i % 4 != 3)
    x, y = frame['offset']; width, height = frame['size']
    assert 6 <= x and 6 <= y and x+width <= 554 and y+height <= 474

app.PinkMenu.activate = False
app.PinkMenu.extra_style = 0x08000000
native_open = app.PinkMenu.open
def hidden_open(self, x, y):
    native_open(self, x, y)
    app.user.ShowWindow(self.hwnd, 0)
app.PinkMenu.open = hidden_open
app.user.SetProcessDPIAware()
app.signature(app.user, 'SendMessageW', app.LRESULT, app.W.HWND, app.W.UINT, app.WPARAM, app.LPARAM)
settings = app.SETTINGS.read_bytes() if app.SETTINGS.exists() else None
pet = app.DesktopPet()
pet.qa_target = 'test'
app.user.ShowWindow(pet.hwnd, 0)


def pump(seconds):
    until = time.perf_counter()+seconds
    message = app.W.MSG()
    while time.perf_counter() < until:
        while app.user.PeekMessageW(C.byref(message), None, 0, 0, 1):
            # Synthetic input below is sent synchronously. Do not let unrelated
            # hardware mouse movement alter this hidden-window test gesture.
            if message.hWnd == pet.hwnd and 0x0200 <= message.message <= 0x020E:
                continue
            app.user.TranslateMessage(C.byref(message))
            app.user.DispatchMessageW(C.byref(message))
        pet.tick()
        time.sleep(.003)


def mouse(message, x, y, buttons=1):
    def position(pointer):
        point = C.cast(pointer, C.POINTER(app.POINT)).contents
        point.x, point.y = x, y
        return True
    with patch.object(app.user, 'GetCursorPos', side_effect=position):
        app.user.SendMessageW(pet.hwnd, message, buttons, 0)
    assert pet.bits, 'Interaction closed the pet'


def prepare(name='reading', paused=False):
    app.user.ReleaseCapture()
    pet.reset_drag()
    pet.drag_motion.clear()
    pet.stomp_motion.clear()
    pet.clock.current = pet.current = name
    pet.clock.pending = None
    pet.clock.position = pet.elapsed = .7
    pet.paused = paused
    pet.last_stomp_time = float('-inf')
    pet.x, pet.y = 300, 200
    app.user.SetWindowPos(pet.hwnd, None, pet.x, pet.y, 0, 0, 0x0001 | 0x0004 | 0x0010)
    index = app.bisect_right(pet.animations[name]['endpoints'], pet.elapsed)
    pet.draw(index)
    pet.last_tick = time.perf_counter()
    x, y = pet.x+100, pet.y+100
    mouse(0x0201, x, y)
    return x, y


def shake(x, y):
    for offset in (55, -55, 55, -55, 55, -55):
        mouse(0x0200, x+offset, y)
        pump(.075)
    assert pet.dragging and pet.shake.armed and pet.drag_motion.active, {
        'dragging': pet.dragging, 'armed': pet.shake.armed, 'used': pet.shake.used,
        'active': pet.drag_motion.active, 'points': list(pet.shake.points)}


try:
    x, y = prepare()
    for step in range(1, 8):
        mouse(0x0200, x+step*15, y)
        pump(.03)
    mouse(0x0202, x+105, y, 0)
    pump(.25)
    assert not pet.stomp_motion.visible and pet.expression_key in ('hide', 'hello')

    for name in ('standing', 'drinking', 'reading'):
        x, y = prepare(name)
        shake(x, y)
        held = pet.clock.position
        mouse(0x0202, x-55, y, 0)
        assert pet.stomp_motion.visible and pet.expression_key == 'shake_angry'
        drag_elapsed=pet.drag_motion.elapsed
        pump(.1)
        assert pet.drag_motion.visible and pet.drag_motion.elapsed > drag_elapsed
        pump(.25)
        assert pet.visual_pose == 'stomping' and pet.clock.position == 0 and pet.current == 'standing'
        if name == 'standing':
            preview = Image.new('RGBA', (pet.width, pet.height), '#eadfe7')
            preview.alpha_composite(Image.frombytes('RGBA', (pet.width, pet.height),
                                    C.string_at(pet.bits, pet.width*pet.height*4), 'raw', 'BGRA'))
            preview.convert('RGB').save(ROOT/'work'/'stomping-native.jpg')
        pump(duration-.1)
        assert not pet.stomp_motion.visible and pet.current == 'standing'
        assert .2 < pet.clock.position < .65
        assert pet.stomp_motion.held_frame is None

    # A cold archive must keep the previous image on screen while preparing;
    # its I/O time must not consume the beginning of the reaction.
    x,y=prepare(paused=True)
    pet.reset_drag()
    pet.stream.clear()
    native_read=pet.stream.archive.read
    def slow_read(*args):
        time.sleep(.025)
        return native_read(*args)
    with patch.object(pet.stream.archive,'read',side_effect=slow_read), patch.object(pet,'play_stomp_voice') as voice:
        started=time.perf_counter()
        assert pet.start_stomp(started)
        assert time.perf_counter()-started < .05
        pet.tick()
        assert pet.stomp_motion.preparing and pet.stomp_motion.elapsed == 0
        voice.assert_not_called()
        pump(.13)
        assert not pet.stomp_motion.preparing and 0 < pet.stomp_motion.elapsed < .13
        voice.assert_called_once()
        pump(duration+.2)
        voice.assert_called_once()
    assert not pet.stomp_motion.visible and pet.clock.position == 0 and pet.current == 'standing'

    x,y=prepare('drinking')
    pet.reset_drag()
    pet.clock.position=pet.elapsed=pet.animations['drinking']['duration']-.08
    pet.clock.request('reading')
    pet.draw(len(pet.animations['drinking']['frames'])-5)
    assert pet.start_stomp(time.perf_counter())
    pump(duration-.12)
    assert pet.stomp_motion.visible and pet.current == 'standing'
    pump(.35)
    assert not pet.stomp_motion.visible and pet.current == 'standing' and pet.clock.pending is None
    assert 0 < pet.clock.position < .6

    # A new explicit menu selection made during the reaction is still queued
    # against normal standing, rather than reviving the interrupted old pose.
    x,y=prepare('reading')
    pet.reset_drag()
    assert pet.start_stomp(time.perf_counter())
    pet.switch('drinking')
    pump(duration+.15)
    assert pet.current == 'standing' and pet.clock.pending == 'drinking'

    x, y = prepare(paused=True)
    shake(x, y)
    held = pet.clock.position
    pump(.28)
    assert pet.dragging and pet.stomp_motion.visible and pet.expression_key == 'shake_angry'
    pump(.16)
    entry, base = pet.displayed_frame, pet.stomp_motion.held_frame
    mouse(0x0200, x+70, y)
    assert not pet.stomp_motion.visible and pet.drag_motion.active
    assert pet.drag_motion.entry_frame is entry and pet.drag_motion.held_frame is base
    pump(.2)
    mouse(0x0202, x+70, y, 0)
    pump(.3)
    assert not pet.drag_motion.visible and not pet.stomp_motion.visible
    assert pet.paused and pet.clock.position == 0 and pet.current == 'standing'

    x, y = prepare(paused=True)
    shake(x, y)
    mouse(0x0202, x-55, y, 0)
    pump(.3)
    pet.resize(1.0)
    assert pet.stomp_motion.visible and pet.visual_pose == 'stomping'
    pump(duration)
    assert pet.paused and pet.clock.position == 0 and pet.current == 'standing' and not pet.stomp_motion.visible

    x, y = prepare()
    shake(x, y)
    app.user.SendMessageW(pet.hwnd, 0x0215, 0, 0)
    pump(.3)
    assert not pet.stomp_motion.visible and not pet.dragging

    x, y = prepare()
    pet.last_stomp_time = time.perf_counter()
    shake(x, y)
    mouse(0x0202, x-55, y, 0)
    pump(.25)
    assert not pet.stomp_motion.visible, 'Cooldown did not suppress rapid repetition'

    pet.show_expression('shake_angry')
    pet.expression_expires_at = time.perf_counter()-.01
    pump(.03)
    assert pet.expression is None and pet.expression_key is None
    assert pet.stream.peak_cache_frames <= 12 and pet.stream.peak_cache_bytes <= 24*1024**2
    report = {'horizontal_vertical_diagonal_shakes': True, 'ordinary_drag_jitter_slow_motion_rejected': True,
              'one_shot_after_release_or_idle': True, 'all_three_main_actions_recover_normal_standing': True,
              'stomp_and_secret_sticker_together': True, 'picker_remains_nine_stickers': True,
              'paused_playback_and_resize': True, 'regrab_smoothly_cancels_stomp': True,
              'capture_loss_cancels_pending_shake': True, 'cooldown_and_expression_timeout': True,
              'all_frames_valid_premultiplied_with_margins': count, 'shared_bounded_cache': True}
    report.update(live_outgoing_motion_during_fade=True,cold_start_is_nonblocking_and_preserves_intro=True,
                  main_action_continues_after_exact_idle_endpoint=True,one_voice_dispatch_after_frames_ready=True,
                  old_pending_action_cancelled_new_menu_selection_preserved=True)
    (ROOT/'work'/'shaking-validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
finally:
    app.user.DestroyWindow(pet.hwnd)
    if settings is not None:
        app.SETTINGS.write_bytes(settings)
