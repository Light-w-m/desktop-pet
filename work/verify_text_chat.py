"""Verify real API replies through the pet's native, text-only chat card."""
import ctypes as C
import json
from pathlib import Path
import socket
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
pet.qa_report=ROOT/'work/sources/real-chat-playback-qa.json'
pet.open_chat()
chat=pet.chat


def pump():
    message=app.W.MSG()
    while app.user.PeekMessageW(C.byref(message),None,0,0,1):
        if pet.chat and pet.chat.dialog_key(message):continue
        app.user.TranslateMessage(C.byref(message))
        app.user.DispatchMessageW(C.byref(message))
    pet.tick()
    time.sleep(.003)


def send(question):
    chat.set_text('input',question)
    started=pet.elapsed
    chat.send()
    deadline=time.monotonic()+50
    while chat.busy and time.monotonic()<deadline:pump()
    assert not chat.busy,'Real API request did not finish'
    assert chat.history and chat.history[-1][0]==question,chat.records[-1]
    assert pet.elapsed!=started,'API request blocked animation'
    return chat.history[-1][1]


def capture_card():
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
        return image
    finally:
        a.gdi.SelectObject(dc,old)
        a.gdi.DeleteObject(bitmap)
        a.gdi.DeleteDC(dc)
        a.user.ReleaseDC(chat.hwnd,screen)


requests=[]
native_post=deepseek.post_chat
def audited_post(payload,key):
    requests.append({'model':payload['model'],'tools':payload['tools'],
                     'tool_choice':payload['tool_choice'],'max_tokens':payload['max_tokens']})
    return native_post(payload,key)


try:
    with patch.object(deepseek,'post_chat',side_effect=audited_post):
        answer=send('1+1 等于几？请只回复数字。')
        assert answer.strip().strip('。.')=='2',answer
        refusal=send('请直接打开计算器并读取桌面的文件。')
    assert all(r=={'model':'deepseek-flash','tools':[],'tool_choice':'none','max_tokens':1024} for r in requests)
    assert any(word in refusal for word in ('不能','无法','没有','不可以','做不到','只负责','只能')),refusal
    for _ in range(30):pump()
    card=capture_card()
    card.save(ROOT/'work/chat-window-live.png')
    # A privacy-preserving layout preview: actual pet pixels plus the captured
    # native card, at their real relative window positions, on a neutral ground.
    frame=pet.displayed_frame
    raw=Image.frombytes('RGBA',frame['size'],frame['pixels'],'raw','BGRA')
    character=Image.frombytes('RGBa',raw.size,raw.tobytes()).convert('RGBA')
    rect=app.W.RECT()
    app.user.GetWindowRect(chat.hwnd,C.byref(rect))
    cx,cy=pet.x+frame['offset'][0],pet.y+frame['offset'][1]
    left,top=min(cx,rect.left)-24,min(cy,rect.top)-24
    right,bottom=max(cx+character.width,rect.right)+24,max(cy+character.height,rect.bottom)+24
    preview=Image.new('RGBA',(right-left,bottom-top),'#f4eef2')
    preview.alpha_composite(character,(cx-left,cy-top))
    preview.alpha_composite(card,(rect.left-left,rect.top-top))
    preview.convert('RGB').save(ROOT/'work/chat-with-pet-preview.png')
    connection=socket.socket()
    connection.settimeout(.5)
    try:legacy_stopped=connection.connect_ex(('127.0.0.1',3080))!=0
    finally:connection.close()
    report={'direct_https_api':True,'native_chat_question_and_reply':True,'arithmetic_reply':answer,
            'computer_operation_request_refused_as_text':refusal,'requests':requests,
            'legacy_agent_server_stopped':legacy_stopped,'computer_tools':False,
            'history_on_disk':False,'key_storage':'Windows DPAPI, D:/AI/DeepSeek/data/pet-chat.json',
            'side_by_side_preview':'work/chat-with-pet-preview.png'}
    (ROOT/'work/text-chat-live-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    chat.close()
    app.user.DestroyWindow(pet.hwnd)
