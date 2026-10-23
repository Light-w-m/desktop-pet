"""Drive only our own native windows: full expression menu/badge lifecycle."""
import ctypes as C
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
sys.argv += ['--qa-seconds', '300', '--qa-assets', str(ROOT/'work'/'repaired-assets')]
from citlali_pet import app as app
from citlali_pet.ui.expressions import EXPRESSIONS, ExpressionPicker
from citlali_pet.ui.pet_menu import monitor_work_area

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


def main_mouse(message, x, y, buttons=1):
    # Keep the real cursor untouched while dispatching to our own window.
    def cursor(pointer):
        point = C.cast(pointer,C.POINTER(app.POINT)).contents
        point.x,point.y = x,y
        return True
    with patch.object(app.user,'GetCursorPos',side_effect=cursor):
        app.user.SendMessageW(pet.hwnd,message,buttons,0)
    assert pet.bits, 'An interaction closed the pet'


try:
    app.signature(app.user,'GetClassLongW',app.W.DWORD,app.W.HWND,C.c_int)
    assert app.user.GetClassLongW(pet.hwnd,-26) & 8, 'Native double-click events are disabled'
    pet.x,pet.y = 400,300
    app.user.SetWindowPos(pet.hwnd,None,pet.x,pet.y,0,0,0x0001 | 0x0004 | 0x0010)
    start_x,start_y = pet.x+100,pet.y+100
    main_mouse(0x0201,start_x,start_y)
    main_mouse(0x0200,start_x+1,start_y+1)
    main_mouse(0x0202,start_x+1,start_y+1,0)
    assert pet.expression is None and (pet.x,pet.y) == (400,300), 'A click/jitter triggered a drag'
    with patch.object(pet.interaction_random,'choice',side_effect=['annoyed','blush','hide','hello']) as choose:
        for key in ('annoyed','blush'):
            main_mouse(0x0201,start_x,start_y)
            main_mouse(0x0202,start_x,start_y,0)
            main_mouse(0x0203,start_x,start_y)
            main_mouse(0x0202,start_x,start_y,0)
            assert pet.expression_key == key
            ready(pet.expression)
            assert choose.call_args.args[0] == ('annoyed','blush')
        for key in ('hide','hello'):
            start_x,start_y = pet.x+100,pet.y+100
            old_x,old_y = pet.x,pet.y
            dx,dy = max(30,abs(app.user.GetSystemMetrics(68))+10),max(20,abs(app.user.GetSystemMetrics(69))+10)
            main_mouse(0x0201,start_x,start_y)
            main_mouse(0x0200,start_x+dx,start_y+dy)
            assert pet.dragging and pet.expression_key == key
            assert (pet.x,pet.y) == (old_x+dx,old_y+dy)
            assert choose.call_args.args[0] == ('hide','hello')
            ready(pet.expression)
            badge,deadline = pet.expression,pet.expression_expires_at
            badge_position = badge.x,badge.y
            calls = choose.call_count
            main_mouse(0x0200,start_x+dx+17,start_y+dy+13)
            assert pet.expression is badge and pet.expression_expires_at == deadline
            assert choose.call_count == calls, 'Continuous dragging retriggered the expression'
            assert (badge.x,badge.y) == (badge_position[0]+17,badge_position[1]+13)
            main_mouse(0x0202,start_x+dx+17,start_y+dy+13,0)
            assert pet.drag_offset is None and not pet.dragging
            with patch.object(app.time,'perf_counter',return_value=deadline):
                pet.tick()
            assert pet.expression is None, 'Interaction expression did not expire'
    # Losing capture or opening a menu cancels a pending drag.
    for cancel in ('capture','menu','button_released'):
        pet.show_expression(None)
        start_x,start_y = pet.x+100,pet.y+100
        main_mouse(0x0201,start_x,start_y)
        if cancel == 'capture':
            app.user.SendMessageW(pet.hwnd,0x0215,0,0)
        elif cancel == 'menu':
            pet.menu()
            pet.popup.close()
        else:
            main_mouse(0x0200,start_x+100,start_y+100,0)
        position = pet.x,pet.y
        main_mouse(0x0200,start_x+150,start_y+150)
        assert (pet.x,pet.y) == position and pet.expression is None
        assert pet.drag_offset is None and pet.drag_origin is None and not pet.dragging
        app.user.ReleaseCapture()
    pet.last_tick = time.perf_counter()
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
              'native_double_click_both_reactions': True,'drag_both_reactions_and_follow': True,
              'single_click_and_jitter_ignored': True,'one_reaction_per_drag_and_five_second_timeout': True,
              'capture_menu_and_button_release_cancel_drag': True,
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
