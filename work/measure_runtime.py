"""Run the packaged QA cycle and sample its own windows' memory usage."""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
exe = ROOT/'work'/'dist'/'CitlaliDesktopPet.exe'
import sys
scale = float(sys.argv[1]) if len(sys.argv)>1 else 1.0
settings = exe.parent/'pet-settings.json'
saved_settings = settings.read_bytes() if settings.exists() else None
settings.write_text(json.dumps({'scale':scale}),encoding='utf-8')
user = C.WinDLL('user32', use_last_error=True)
kernel = C.WinDLL('kernel32', use_last_error=True)
psapi = C.WinDLL('psapi', use_last_error=True)
callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
user.EnumWindows.argtypes = [callback, W.LPARAM]
user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user.ShowWindow.argtypes = [W.HWND, C.c_int]
kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel.OpenProcess.restype = W.HANDLE
kernel.CloseHandle.argtypes = [W.HANDLE]
kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]


class MEMORY(C.Structure):
    _fields_ = [('cb', W.DWORD), ('PageFaultCount', W.DWORD)] + [
        (name, C.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]


psapi.GetProcessMemoryInfo.argtypes = [W.HANDLE, C.POINTER(MEMORY), W.DWORD]
process = subprocess.Popen([str(exe), '--qa-seconds', '45'], creationflags=subprocess.CREATE_NO_WINDOW)
samples = []
started = time.perf_counter()


def memory(pid):
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        return None
    try:
        data = MEMORY()
        data.cb = C.sizeof(data)
        if psapi.GetProcessMemoryInfo(handle, C.byref(data), C.sizeof(data)):
            return {'working': data.WorkingSetSize, 'private': data.PrivateUsage}
    finally:
        kernel.CloseHandle(handle)


@callback
def inspect(hwnd, unused):
    name = C.create_unicode_buffer(128)
    user.GetClassNameW(hwnd, name, len(name))
    if name.value != 'CitlaliDesktopPetWindow_20261014':
        return True
    pid = W.DWORD()
    user.GetWindowThreadProcessId(hwnd, C.byref(pid))
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return True
    try:
        path = C.create_unicode_buffer(32768)
        length = W.DWORD(len(path))
        if kernel.QueryFullProcessImageNameW(handle, 0, path, C.byref(length)) and Path(path.value).resolve() == exe.resolve():
            # Keep automated measurements separate from the interactive pet.
            user.ShowWindow(hwnd, 0)
            data = memory(pid.value)
            if data:
                samples.append({'time':time.perf_counter(), 'child':data,'launcher':memory(process.pid)})
    finally:
        kernel.CloseHandle(handle)
    return True


while process.poll() is None:
    if time.perf_counter()-started > 100:
        raise RuntimeError('Packaged QA did not finish within 100 seconds')
    user.EnumWindows(inspect, 0)
    time.sleep(.2)
assert process.returncode == 0 and samples
if saved_settings is None:
    settings.unlink(missing_ok=True)
else:
    settings.write_bytes(saved_settings)
report = {'display_scale':scale,'samples':len(samples),
          'child_peak_working_mib': max(s['child']['working'] for s in samples)/1024/1024,
          'child_peak_private_mib': max(s['child']['private'] for s in samples)/1024/1024,
          'group_peak_working_mib': max(s['child']['working']+(s['launcher'] or {}).get('working',0) for s in samples)/1024/1024,
          'group_peak_private_mib': max(s['child']['private']+(s['launcher'] or {}).get('private',0) for s in samples)/1024/1024}
(ROOT/'work'/'memory-after.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
