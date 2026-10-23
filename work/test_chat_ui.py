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
from PIL import Image, ImageDraw

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


def screenshot(chat, name='chat-window-preview.png'):
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
        image=Image.frombytes('RGB',(chat.width,chat.height),buffer.raw,'raw','BGRX').convert('RGBA')
        mask=Image.new('L',image.size)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,chat.width-1,chat.height-1),radius=round(9*chat.dpi),fill=255)
        image.putalpha(mask)
        image.save(ROOT/'work'/name)
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
    view=chat.transcript
    sent,received=view.bubbles
    assert sent['role']=='user' and received['role']=='assistant'
    assert sent['x']>received['x'], 'User and pet messages were not separated by side'
    assert view.COLOURS['user']!=view.COLOURS['assistant']
    assert chat.text('transcript')=='你好呀\r\n\r\n你好，我在这里。今天想聊些什么？'
    assert received['y']>=sent['y']+sent['height'], 'Consecutive bubbles overlap'
    screenshot(chat)
    # Native EDIT wrapping includes explicit newlines, CJK, emoji and long
    # unbroken strings. The entire bubble scrolls rather than clipping a reply.
    long_text=('第一段：这是长消息，应该在气泡内部自动换行。'*12+'\n第二段 😀 & 文本\n'+'https://example.com/'+'a'*400)
    chat.records=[('user','帮我看看这段多行文字\n换行后也放在同一个气泡里'),('assistant',long_text)]
    chat.render_transcript()
    received=view.bubbles[-1]
    assert received['lines']>10 and view.maximum>0
    assert view.offset==view.maximum, 'New messages did not scroll to the bottom'
    client=app.W.RECT()
    app.user.GetClientRect(view.hwnd,C.byref(client))
    assert all(b['x']>=0 and b['x']+b['width']<=client.right for b in view.bubbles)
    assert app.user.SendMessageW(received['hwnd'],0x000E,0,0)==len(long_text.replace('\n','\r\n'))+1  # emoji is two UTF-16 units
    app.user.SendMessageW(received['hwnd'],0x00B1,0,5)
    start_sel,end_sel=app.W.DWORD(),app.W.DWORD()
    app.user.SendMessageW(received['hwnd'],0x00B0,C.addressof(start_sel),C.addressof(end_sel))
    assert (start_sel.value,end_sel.value)==(0,5), 'Bubble text cannot be selected for copying'
    app.user.SendMessageW(view.hwnd,0x0115,6,0)
    assert view.offset==0, 'Scrollbar cannot reach the beginning of a long message'
    pump(.05)
    screenshot(chat,'chat-window-long-preview.png')
    app.user.SendMessageW(received['hwnd'],0x020A,((-120)&0xffff)<<16,0)
    assert view.offset>0, 'Wheel over message text did not scroll the conversation'
    app.user.SendMessageW(view.hwnd,0x0115,6,0)
    chat.records.append(('assistant','新回复不会打断你查看前面的消息。'))
    chat.render_transcript()
    assert view.offset==0, 'An incoming reply interrupted history reading'
    chat.records.append(('user','我发送新消息后回到最新位置'))
    chat.render_transcript()
    assert view.offset==view.maximum
    app.user.SendMessageW(view.hwnd,0x0115,7,0)
    assert view.offset==view.maximum
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
    result.update(user_bubbles_right_pet_bubbles_left=True,distinct_bubble_colours=True,
                  no_sender_name_prefixes=True,long_multiline_and_unbroken_text_wraps=True,
                  scroll_wheel_over_bubbles_and_scrollbar=True,preserve_history_reading_position=True,
                  plain_text_selectable_for_copy=True)
    (ROOT/'work/chat-ui-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    if pet.chat:pet.chat.close()
    app.user.DestroyWindow(pet.hwnd)
