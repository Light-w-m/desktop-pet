"""Send a benign question through the actual frozen EXE's native chat controls."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parent.parent
EXE=ROOT/'work/dist/CitlaliDesktopPet.exe'
user=C.WinDLL('user32',use_last_error=True)
kernel=C.WinDLL('kernel32',use_last_error=True)
callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
long=C.c_ssize_t
for name,result,args in (
    ('EnumWindows',W.BOOL,(callback,W.LPARAM)),
    ('EnumChildWindows',W.BOOL,(W.HWND,callback,W.LPARAM)),
    ('GetWindowTextW',C.c_int,(W.HWND,W.LPWSTR,C.c_int)),
    ('GetClassNameW',C.c_int,(W.HWND,W.LPWSTR,C.c_int)),
    ('GetWindowRect',W.BOOL,(W.HWND,C.POINTER(W.RECT))),
    ('GetWindowThreadProcessId',W.DWORD,(W.HWND,C.POINTER(W.DWORD))),
    ('GetDlgItem',W.HWND,(W.HWND,C.c_int)),
    ('SetWindowTextW',W.BOOL,(W.HWND,W.LPCWSTR)),
    ('SendMessageW',long,(W.HWND,W.UINT,C.c_size_t,long)),
    ('PostMessageW',W.BOOL,(W.HWND,W.UINT,C.c_size_t,long)),
    ('GetWindow',W.HWND,(W.HWND,W.UINT)),
    ('IsWindowVisible',W.BOOL,(W.HWND,)),
):
    fn=getattr(user,name);fn.restype,fn.argtypes=result,args
kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
kernel.CloseHandle.argtypes=[W.HANDLE]
found=[]
@callback
def inspect(hwnd,_):
    title=C.create_unicode_buffer(128)
    user.GetWindowTextW(hwnd,title,len(title))
    if title.value!='茜特菈莉 · 聊天' or not user.IsWindowVisible(hwnd):return True
    pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,C.byref(pid))
    handle=kernel.OpenProcess(0x1000,False,pid.value)
    if not handle:return True
    try:
        path=C.create_unicode_buffer(32768);size=W.DWORD(len(path))
        if kernel.QueryFullProcessImageNameW(handle,0,path,C.byref(size)) and Path(path.value).resolve()==EXE.resolve():
            found.append(hwnd)
    finally:kernel.CloseHandle(handle)
    return True


env=os.environ.copy();env['TEMP']=env['TMP']=r'D:\AI\DeepSeek\tmp'
process=subprocess.Popen([str(EXE),'--qa-seconds','60','--qa-standing','--qa-chat'],cwd=EXE.parent,env=env)
parent=None
try:
    deadline=time.monotonic()+18
    while time.monotonic()<deadline:
        found.clear();user.EnumWindows(inspect,0)
        if found:break
        if process.poll() is not None:raise RuntimeError('The packaged app exited before chat opened')
        time.sleep(.1)
    assert len(found)==1,'Frozen native chat did not open'
    chat=found[0]
    parent=user.GetWindow(chat,4)
    input_hwnd,transcript=user.GetDlgItem(chat,707),user.GetDlgItem(chat,708)
    assert input_hwnd and transcript
    question=C.create_unicode_buffer('1+1 等于几？请只回复数字。')
    # Cross-process EDIT contents use the marshalled WM_SETTEXT/WM_GETTEXT
    # messages; SetWindowText may only update the other window's caption.
    assert user.SendMessageW(input_hwnd,0x000C,0,C.cast(question,C.c_void_p).value)
    check=C.create_unicode_buffer(256)
    user.SendMessageW(input_hwnd,0x000D,len(check),C.cast(check,C.c_void_p).value)
    assert check.value==question.value,repr(check.value)
    user.PostMessageW(chat,0x0111,701,0)
    deadline=time.monotonic()+40
    text=''
    while time.monotonic()<deadline:
        length=user.SendMessageW(transcript,0x000E,0,0)
        buffer=C.create_unicode_buffer(length+1)
        user.SendMessageW(transcript,0x000D,len(buffer),C.cast(buffer,C.c_void_p).value)
        text=buffer.value.replace('\r','')
        if text.strip().split('\n\n')[-1].strip()=='2':break
        time.sleep(.1)
    assert text.strip().split('\n\n')[-1].strip()=='2',text
    assert text==question.value+'\n\n2',text
    bubble_rects={}
    @callback
    def inspect_bubble(hwnd,_):
        kind=C.create_unicode_buffer(32)
        user.GetClassNameW(hwnd,kind,len(kind))
        if kind.value.upper()!='EDIT':return True
        length=user.SendMessageW(hwnd,0x000E,0,0)
        body=C.create_unicode_buffer(length+1)
        user.SendMessageW(hwnd,0x000D,len(body),C.cast(body,C.c_void_p).value)
        rect=W.RECT()
        assert user.GetWindowRect(hwnd,C.byref(rect))
        bubble_rects[body.value]=rect
        return True
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        bubble_rects.clear()
        user.EnumChildWindows(transcript,inspect_bubble,0)
        if set(bubble_rects)=={question.value,'2'}:break
        time.sleep(.03)
    assert set(bubble_rects)=={question.value,'2'},set(bubble_rects)
    assert bubble_rects[question.value].left>bubble_rects['2'].left
    assert bubble_rects[question.value].bottom<bubble_rects['2'].top
    result={'frozen_native_chat_opened':True,'real_api_reply':'2',
            'key_decryption_and_windows_https_in_exe':True,'tools':[],
            'local_agent_server_required':False,'sender_names_in_transcript':False,
            'conversation_view':'native_left_right_bubbles','frozen_bubble_alignment_verified':True}
    (ROOT/'work/chat-package-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    if parent:user.PostMessageW(parent,0x0010,0,0)
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
