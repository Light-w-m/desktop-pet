"""Exercise only the pet's own Win32 chat controls and asynchronous replies."""
import ctypes as C
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
sys.argv += ['--qa-seconds','120','--qa-assets',str(ROOT/'work/repaired-assets')]
from citlali_pet import app
from citlali_pet.ui import deepseek
from PIL import Image

app.user.SetProcessDPIAware()
pet=app.DesktopPet()
app.user.ShowWindow(pet.hwnd,0)
pet.qa_report=ROOT/'work/sources/chat-playback-qa.json'


def pump(seconds=.1):
    end=time.perf_counter()+seconds
    message=app.W.MSG()
    while time.perf_counter()<end:
        while app.user.PeekMessageW(C.byref(message),None,0,0,1):
            if pet.chat and pet.chat.dialog_key(message):continue
            app.user.TranslateMessage(C.byref(message))
            app.user.DispatchMessageW(C.byref(message))
        pet.tick()
        time.sleep(.002)


def screenshot(chat):
    a=app
    a.signature(a.user,'PrintWindow',a.W.BOOL,a.W.HWND,a.W.HDC,a.W.UINT)
    a.signature(a.gdi,'CreateCompatibleBitmap',a.W.HBITMAP,a.W.HDC,C.c_int,C.c_int)
    a.signature(a.gdi,'GetDIBits',C.c_int,a.W.HDC,a.W.HBITMAP,a.W.UINT,a.W.UINT,C.c_void_p,C.POINTER(a.BITMAPINFO),a.W.UINT)
    screen=a.user.GetDC(chat.hwnd)
    dc=a.gdi.CreateCompatibleDC(screen)
    bitmap=a.gdi.CreateCompatibleBitmap(screen,chat.width,chat.height)
    old=a.gdi.SelectObject(dc,bitmap)
    try:
        assert a.user.PrintWindow(chat.hwnd,dc,2)
        a.gdi.SelectObject(dc,old)
        info=a.BITMAPINFO()
        info.bmiHeader.biSize=C.sizeof(a.BITMAPINFOHEADER)
        info.bmiHeader.biWidth,info.bmiHeader.biHeight=chat.width,-chat.height
        info.bmiHeader.biPlanes,info.bmiHeader.biBitCount=1,32
        buffer=C.create_string_buffer(chat.width*chat.height*4)
        assert a.gdi.GetDIBits(dc,bitmap,0,chat.height,buffer,C.byref(info),0)
        Image.frombytes('RGB',(chat.width,chat.height),buffer.raw,'raw','BGRX').save(ROOT/'work/chat-window-preview.png')
    finally:
        a.gdi.SelectObject(dc,old)
        a.gdi.DeleteObject(bitmap)
        a.gdi.DeleteDC(dc)
        a.user.ReleaseDC(chat.hwnd,screen)


try:
    pet.open_chat()
    chat=pet.chat
    pump(.15)
    assert chat.hwnd and chat.controls['input']
    # Use the actual ctypes MSG layout from the runtime and exercise the same
    # keyboard-routing path as the executable's main message loop.
    message=app.W.MSG()
    message.hWnd=chat.controls['input']
    message.message,message.wParam=0x0100,9
    assert chat.dialog_key(message), 'Native Tab navigation was not handled'
    message.wParam=65
    assert not chat.dialog_key(message), 'Ordinary typing was intercepted'
    rect=app.W.RECT()
    app.user.GetWindowRect(chat.hwnd,C.byref(rect))
    bounds=pet.popup_bounds()
    assert rect.left>=bounds[2] or rect.right<=bounds[0], 'Chat covered the character'
    start=pet.elapsed
    calls=[]
    def reply(question,history):
        calls.append((question,history))
        time.sleep(.25)
        return '你好，我在这里。今天想聊些什么？'
    with patch.object(deepseek,'load_api_key',return_value='sk-test-only-12345678'),patch.object(deepseek,'ask',side_effect=reply):
        chat.set_text('input','你好呀')
        chat.invoke(chat.SEND)
        assert chat.busy
        pump(.5)
        assert not chat.busy and chat.history==[('你好呀','你好，我在这里。今天想聊些什么？')]
        assert calls==[('你好呀',[])]
        assert pet.elapsed>start+.25,'Chat request blocked playback'
        assert '你好，我在这里' in chat.text('transcript')
    screenshot(chat)
    original=rect.left
    pet.x+=40
    chat.follow()
    app.user.GetWindowRect(chat.hwnd,C.byref(rect))
    assert rect.left!=original,'Chat did not follow the pet'
    chat.show_settings(True)
    assert chat.settings_visible and chat.text('key')=='', 'Saved key was exposed in the input'
    chat.show_settings(False)
    chat.invoke(chat.CLEAR)
    assert not chat.history and not chat.records
    chat.close()
    assert pet.bits,'Closing chat closed the pet'
    chat.open()
    pump(.1)
    chat.close()
    result={'native_input_and_plain_text_reply':True,'right_side_or_edge_fallback':True,
            'follows_pet':True,'request_does_not_block_animation':True,
            'clear_history_and_reopen':True,'key_input_never_prefilled':True,
            'close_does_not_exit_pet':True,'computer_tools':False}
    result['native_message_loop_and_tab_navigation']=True
    (ROOT/'work/chat-ui-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    if pet.chat:pet.chat.close()
    app.user.DestroyWindow(pet.hwnd)
