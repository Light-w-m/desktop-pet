"""Exercise the real layered popup and controls without touching other apps."""
import ctypes as C
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.argv += ['--qa-seconds', '120']
sys.argv += ['--qa-assets', str(ROOT/'work'/'repaired-assets')]
import desktop_pet as app
from menu_view import HITS
from PIL import Image

# Send messages only to these test windows, without stealing the user's focus.
app.PinkMenu.activate = False
app.PinkMenu.extra_style = 0x08000000
native_open = app.PinkMenu.open


def open_hidden(self, x, y):
    native_open(self, x, y)
    app.user.ShowWindow(self.hwnd, 0)


app.PinkMenu.open = open_hidden

app.user.SetProcessDPIAware()
app.signature(app.user, 'SendMessageW', app.LRESULT, app.W.HWND, app.W.UINT, app.WPARAM, app.LPARAM)
app.signature(app.user, 'GetGuiResources', app.W.DWORD, app.W.HANDLE, app.W.DWORD)
app.signature(app.kernel, 'GetCurrentProcess', app.W.HANDLE)
pet = app.DesktopPet()
app.user.ShowWindow(pet.hwnd, 0)
pet.qa_report = ROOT/'work'/'menu-playback-qa.json'


def pump(seconds=.05):
    end = time.perf_counter()+seconds
    message = app.W.MSG()
    while time.perf_counter() < end:
        while app.user.PeekMessageW(C.byref(message), None, 0, 0, 1):
            app.user.TranslateMessage(C.byref(message))
            app.user.DispatchMessageW(C.byref(message))
        pet.tick()
        time.sleep(.002)


def send(message, wparam=0, lparam=0):
    return app.user.SendMessageW(pet.popup.hwnd, message, wparam, lparam)


def click(command):
    rect = HITS[command]
    x = round((rect[0]+rect[2])/2*pet.popup.dpi)
    y = round((rect[1]+rect[3])/2*pet.popup.dpi)
    position = x | (y << 16)
    send(0x0200, 0, position)
    send(0x0201, 1, position)
    send(0x0202, 0, position)
    assert pet.popup is None


try:
    pet.menu()
    pump(.15)
    popup = pet.popup
    pixels = C.string_at(popup.bits, popup.width*popup.height*4)
    Image.frombytes('RGBA', (popup.width, popup.height), pixels, 'raw', 'BGRA').save(ROOT/'work'/'pink-menu-native.png')
    start = pet.elapsed
    pump(.25)
    assert pet.elapsed > start+.15, 'Opening the menu stopped animation'
    dispatch_ms = []
    for command in list(HITS)*2:
        rect = HITS[command]
        x = round((rect[0]+rect[2])/2*pet.popup.dpi)
        y = round((rect[1]+rect[3])/2*pet.popup.dpi)
        begin = time.perf_counter()
        send(0x0200, 0, x | (y << 16))
        dispatch_ms.append((time.perf_counter()-begin)*1000)
        pump(.017)
    assert max(dispatch_ms) < 25, 'Hover painting blocked the animation thread'
    send(0x0100, 27)
    assert pet.popup is None and pet.bits, 'Escape closed the pet instead of the menu'
    pet.menu()
    click(12)
    assert pet.clock.pending == 'drinking'
    pet.menu()
    assert pet.popup.last_state['pending'] == 'drinking'
    click(11)
    assert pet.clock.pending is None
    pet.menu()
    click(20)
    assert pet.paused
    pet.menu()
    click(20)
    assert not pet.paused
    pet.menu()
    click(10)
    assert pet.auto
    pet.menu()
    send(0x0100, 36)
    send(0x0100, 40)
    send(0x0100, 13)
    assert not pet.auto and pet.clock.requested == 'standing'
    for command, scale in ((31, .7), (33, 1.3), (32, 1.0)):
        pet.menu()
        click(command)
        assert pet.scale == scale
    pet.menu()
    send(0x0006, 0)  # Outside focus/deactivation closes the popup.
    assert pet.popup is None
    process = app.kernel.GetCurrentProcess()
    before = app.user.GetGuiResources(process, 0)
    for _ in range(20):
        pet.menu()
        send(0x0100, 27)
    after = app.user.GetGuiResources(process, 0)
    assert after <= before+1, ('GDI handles leaked', before, after)
    result = {'native_window_rendered': True, 'menu_keeps_animation_playing': True,
              'mouse_keyboard_pause_auto_resize_dismiss': True, 'gdi_handles_before': before,
              'gdi_handles_after': after, 'max_hover_dispatch_ms':max(dispatch_ms)}
    (ROOT/'work'/'menu-validation.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
finally:
    app.user.DestroyWindow(pet.hwnd)
