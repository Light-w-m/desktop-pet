"""Close this project's pet before replacing its executable."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path

user=C.WinDLL('user32',use_last_error=True)
kernel=C.WinDLL('kernel32',use_last_error=True)
callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
user.EnumWindows.argtypes=[callback,W.LPARAM]
user.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
kernel.CloseHandle.argtypes=[W.HANDLE]
target=(Path(__file__).resolve().parent.parent/'CitlaliDesktopPet.exe').resolve()

@callback
def close(hwnd,param):
    name=C.create_unicode_buffer(128)
    user.GetClassNameW(hwnd,name,len(name))
    if name.value!='CitlaliDesktopPetWindow_20261014':return True
    pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,C.byref(pid))
    handle=kernel.OpenProcess(0x1000,False,pid.value)
    if not handle:return True
    try:
        path=C.create_unicode_buffer(32768);size=W.DWORD(len(path))
        if kernel.QueryFullProcessImageNameW(handle,0,path,C.byref(size)) and Path(path.value).resolve()==target:
            user.PostMessageW(hwnd,0x0010,0,0)
            print('Closed project pet',pid.value)
    finally:kernel.CloseHandle(handle)
    return True

user.EnumWindows(close,0)
