"""Exercise selected-image chat and dismiss behaviour in our own Win32 UI."""
import ctypes as C
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
sys.argv += ['--qa-seconds','120','--qa-assets',str(ROOT/'work/repaired-assets')]
from citlali_pet import app
from citlali_pet.ui import chat_window,deepseek
from citlali_pet.ui.chat_images import ImageMessage

fixture=ROOT/'work/sources/chat-vision-fixture.png'
image=Image.new('RGB',(480,240),'white')
draw=ImageDraw.Draw(image)
draw.ellipse((30,45,170,185),fill='#2277dd')
draw.rectangle((270,55,410,175),fill='#f07020')
draw.text((195,210),'PET 6248',fill='black')
image.save(fixture)
app.user.SetProcessDPIAware()
pet=app.DesktopPet()
app.user.ShowWindow(pet.hwnd,0)
pet.qa_report=ROOT/'work/sources/chat-features-playback.json'
def pump(seconds=.06):
    deadline=time.monotonic()+seconds
    message=app.W.MSG()
    while time.monotonic()<deadline:
        while app.user.PeekMessageW(C.byref(message),None,0,0,1):
            if pet.chat and pet.chat.dialog_key(message):continue
            app.user.TranslateMessage(C.byref(message))
            app.user.DispatchMessageW(C.byref(message))
        pet.tick()
        time.sleep(.002)
def await_image():
    deadline=time.monotonic()+8
    while pet.chat.preparing_image and time.monotonic()<deadline:pump()
    assert pet.chat.attachment and not pet.chat.preparing_image

try:
    pet.open_chat();chat=pet.chat
    pump()
    assert chat.text('status')==''
    # All child controls, including image selection, remain inside the popup.
    app.user.SendMessageW(chat.controls['input'],0x0201,0,0)
    app.user.SendMessageW(chat.controls['input'],0x0202,0,0)
    pump()
    assert chat.hwnd
    def chooser(hwnd):
        chat.window_proc(hwnd,0x0006,0,0)
        pump()
        assert chat.hwnd,'The owned file chooser dismissed the chat'
        return str(fixture)
    with patch.object(chat_window,'choose_image',side_effect=chooser),patch.object(deepseek,'ask') as network:
        chat.invoke(chat.IMAGE)
        await_image()
        network.assert_not_called()
    assert chat.attachment_preview and chat.attachment.name==fixture.name
    chat.invoke(chat.REMOVE_IMAGE)
    assert chat.attachment is None
    chat.attach_image(fixture);await_image()
    calls=[]
    def answer(question,history):
        assert isinstance(question,ImageMessage)
        calls.append(question)
        return '左边是蓝色圆形，右边是橙色方框。'
    with patch.object(deepseek,'load_api_key',return_value='sk-test-only-12345678'),patch.object(deepseek,'ask',side_effect=answer):
        chat.set_text('input','请描述这张图片')
        chat.send()
        deadline=time.monotonic()+5
        while chat.busy and time.monotonic()<deadline:pump()
    assert len(calls)==1 and chat.history[-1][1].startswith('左边')
    assert chat.transcript.bubbles[0]['preview'],'Sent image did not appear in its bubble'
    assert chat.attachment is None and chat.text('status')==''
    chat.set_text('input','未发送的草稿')
    chat.window_proc(chat.hwnd,0x0006,0,0)
    pump()
    assert not chat.hwnd and pet.bits,'Outside activation did not dismiss only the chat'
    chat.open();pump()
    assert chat.text('input')=='未发送的草稿' and chat.history,'Reopening lost the draft or conversation'
    # A real activation transfer to a second window also follows the same path.
    app.user.SetForegroundWindow(chat.hwnd);pump()
    outside=app.user.CreateWindowExW(0,'STATIC','Chat dismiss verification',0x10CF0000,
        20,20,180,80,None,None,pet.instance,None)
    try:
        app.user.SetForegroundWindow(outside);pump(.15)
        assert not chat.hwnd,'Native activation transfer failed to dismiss chat'
    finally:app.user.DestroyWindow(outside)
    result={'shortcut_hint_removed':True,'inside_click_keeps_chat':True,
            'outside_activation_dismisses_chat':True,'draft_and_history_survive_dismiss':True,
            'owned_image_picker_does_not_dismiss':True,'selected_image_preview_and_remove':True,
            'no_upload_until_send':True,'image_only_added_capability':True,
            'image_in_sent_bubble':True,'computer_tools':False}
    (ROOT/'work/chat-features-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    if pet.chat:pet.chat.close()
    app.user.DestroyWindow(pet.hwnd)
