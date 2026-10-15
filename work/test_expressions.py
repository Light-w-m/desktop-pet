"""Drive only our own native windows: full expression menu/badge lifecycle."""
import ctypes as C
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.argv += ['--qa-seconds', '300', '--qa-assets', str(ROOT/'work'/'repaired-assets')]
import desktop_pet as app
from expressions import EXPRESSIONS, ExpressionPicker
from pet_menu import monitor_work_area

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


def pump(seconds=.06):
    end = time.perf_counter()+seconds
    message = app.W.MSG()
    while time.perf_counter() < end:
        while app.user.PeekMessageW(C.byref(message), None, 0, 0, 1):
            app.user.TranslateMessage(C.byref(message))
            app.user.DispatchMessageW(C.byref(message))
        pet.tick()
        time.sleep(.002)


def ready(window):
    end = time.perf_counter()+8
    while window.paint_future is not None:
        assert time.perf_counter() < end, 'Popup rendering did not finish'
        pump(.015)


def click(command):
    popup = pet.popup
    rect = popup.hits[command]
    x = round((rect[0]+rect[2])/2*popup.dpi)
    y = round((rect[1]+rect[3])/2*popup.dpi)
    for message in (0x0200, 0x0201, 0x0202):
        app.user.SendMessageW(popup.hwnd, message, message == 0x0201, x | (y << 16))


def picker():
    pet.menu()
    click(50)
    assert isinstance(pet.popup, ExpressionPicker)
    ready(pet.popup)


def snapshot(window, path):
    pixels = C.string_at(window.bits, window.width*window.height*4)
    Image.frombytes('RGBA', (window.width, window.height), pixels, 'raw', 'BGRA').save(path)


try:
    picker()
    snapshot(pet.popup, ROOT/'work'/'expression-picker-native.png')
    before_elapsed = pet.elapsed
    pump(.3)
    assert pet.elapsed > before_elapsed+.2, 'Gallery blocked animation'
    for i, (key, label) in enumerate(EXPRESSIONS):
        if pet.popup is None:
            picker()
        click(101+i)
        assert pet.popup is None and pet.expression_key == key
        badge = pet.expression
        ready(badge)
        assert badge.hwnd and badge.key == key
        alpha = C.string_at(badge.bits, badge.width*badge.height*4)[3::4]
        assert min(alpha) == 0 and max(alpha) == 255
        assert sum(a > 20 for a in alpha) > len(alpha)*.15
        assert app.user.SendMessageW(badge.hwnd, 0x0084, 0, 0) == -1, 'Sticker intercepted mouse'
        assert app.user.SendMessageW(badge.hwnd, 0x0021, 0, 0) == 3, 'Sticker activated itself'
    pet.paused = True
    pet.x, pet.y = 400, 450
    pet.expression.follow()
    original = (pet.expression.x, pet.expression.y)
    pet.x += 87
    pet.y += 41
    app.user.SetWindowPos(pet.hwnd, None, pet.x, pet.y, 0, 0, 0x0001 | 0x0004 | 0x0010)
    assert (pet.expression.x, pet.expression.y) == (original[0]+87, original[1]+41)
    # Breathing frames keep the same badge location.
    stable = (pet.expression.x, pet.expression.y)
    for frame in (0, 20, 80, 152):
        pet.draw(frame)
        assert (pet.expression.x, pet.expression.y) == stable
    for scale in (.7, 1.3, 1):
        pet.resize(scale)
        ready(pet.expression)
        assert pet.expression.width == round(136*scale)
    for current in ('standing', 'reading', 'drinking'):
        pet.current = current
        pet.expression.follow()
        area = monitor_work_area(app, pet.x+pet.width//2, pet.y+pet.height//2)
        assert area.left <= pet.expression.x <= area.right-pet.expression.width
        assert area.top <= pet.expression.y <= area.bottom-pet.expression.height
    pet.current = 'standing'
    pet.x, pet.y = app.user.GetSystemMetrics(0)-pet.width, 0
    pet.expression.follow()
    area = monitor_work_area(app, pet.x+pet.width//2, pet.y+pet.height//2)
    assert pet.expression.y >= area.top and pet.expression.x+pet.expression.width <= area.right
    pet.menu(picker=True)
    ready(pet.popup)
    assert pet.popup.last_state['expression'] == 'wink'
    click(52)
    assert pet.expression is None and pet.expression_key is None and pet.popup is not None
    # Keyboard uses three columns for vertical movement.
    pet.popup.hover = 101
    app.user.SendMessageW(pet.popup.hwnd, 0x0100, 40, 0)
    assert pet.popup.hover == 104
    app.user.SendMessageW(pet.popup.hwnd, 0x0100, 13, 0)
    assert pet.expression_key == 'hide'
    ready(pet.expression)
    pet.show_expression(None)
    picker()
    click(51)
    assert pet.popup is not None and not isinstance(pet.popup, ExpressionPicker)
    app.user.SendMessageW(pet.popup.hwnd, 0x0100, 27, 0)
    process = app.kernel.GetCurrentProcess()
    before = app.user.GetGuiResources(process, 0)
    for i in range(20):
        picker()
        click(101+i % 9)
        ready(pet.expression)
        pet.show_expression(None)
    pump(.1)
    after = app.user.GetGuiResources(process, 0)
    assert after <= before+1, ('Expression windows leaked GDI handles', before, after)
    pet.paused = False
    pet.x, pet.y = 500, 400
    pet.draw(0)
    pet.show_expression('wink')
    ready(pet.expression)
    # Compose only application-owned layers for a reviewable preview.
    preview = Image.new('RGBA', (pet.width, pet.height+90), '#e6eef5')
    pixels = C.string_at(pet.bits, pet.width*pet.height*4)
    preview.alpha_composite(Image.frombytes('RGBA', (pet.width, pet.height), pixels, 'raw', 'BGRA'), (0, 90))
    badge = pet.expression
    pixels = C.string_at(badge.bits, badge.width*badge.height*4)
    preview.alpha_composite(Image.frombytes('RGBA', (badge.width, badge.height), pixels, 'raw', 'BGRA'),
                            (badge.x-pet.x, badge.y-pet.y+90))
    preview.convert('RGB').save(ROOT/'work'/'expression-pet-preview.jpg')
    # The timeout uses real elapsed time, including when playback is paused.
    pet.paused = True
    pet.show_expression('wink')
    ready(pet.expression)
    pump(4.7)
    assert pet.expression_key == 'wink', 'Expression disappeared before five seconds'
    pet.menu(picker=True)
    ready(pet.popup)
    pump(.4)
    assert pet.expression is None and pet.expression_key is None
    assert pet.expression_expires_at is None
    assert pet.popup.last_state['expression'] is None, 'Picker retained an expired selection'
    pet.popup.close()
    pet.show_expression('panic')
    ready(pet.expression)
    original_deadline = pet.expression_expires_at
    with patch.object(app.time, 'perf_counter', return_value=original_deadline-1):
        pet.show_expression('sleep')
    ready(pet.expression)
    replacement_deadline = pet.expression_expires_at
    assert replacement_deadline == original_deadline+4
    with patch.object(app.time, 'perf_counter', return_value=original_deadline+.01):
        pet.tick()
    assert pet.expression_key == 'sleep', 'Previous selection expired the replacement'
    pet.show_expression('sleep')
    ready(pet.expression)
    assert pet.expression_expires_at != replacement_deadline, 'Reselecting did not restart the timer'
    deadline = pet.expression_expires_at
    pet.resize(.7)
    ready(pet.expression)
    assert pet.expression_expires_at == deadline, 'Resizing restarted the timer'
    with patch.object(app.time, 'perf_counter', return_value=deadline):
        pet.tick()
    assert pet.expression is None, 'Expression survived its expiry boundary'
    pet.show_expression('hello')
    pet.show_expression(None)
    assert pet.expression_expires_at is None, 'Manual clear left a timer active'
    report = {'all_9_selected': True, 'gallery_keeps_animation_playing': True,
              'clear_back_keyboard': True, 'follows_move_resize_action': True,
              'stable_between_frames': True, 'monitor_edges_visible': True,
              'click_through_no_activate': True, 'five_second_timeout_while_paused': True,
              'replacement_reselection_restart_timeout': True, 'resize_preserves_timeout': True,
              'expired_picker_selection_cleared': True, 'gdi_handles_before': before,
              'gdi_handles_after': after, 'small_image_cache': pet.stickers.image.cache_info().currsize}
    (ROOT/'work'/'expression-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)
finally:
    app.user.DestroyWindow(pet.hwnd)
