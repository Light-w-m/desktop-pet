"""Measure the actual EXE's CPU, frame rate and memory for each main action."""
import argparse
from bisect import bisect_right
import ctypes as C
from ctypes import wintypes as W
import json
import hashlib
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe',type=Path,default=ROOT/'work/dist/CitlaliDesktopPet.exe')
parser.add_argument('--label',required=True,choices=('before','after'))
parser.add_argument('--scale',type=float,default=1.3)
args=parser.parse_args()
exe=args.exe.resolve()
settings=exe.parent/'pet-settings.json'
saved_settings=settings.read_bytes() if settings.exists() else None
measurement_settings=(ROOT/'pet-settings.json').read_bytes()
settings.write_bytes(measurement_settings)
kernel=C.WinDLL('kernel32',use_last_error=True)
user=C.WinDLL('user32',use_last_error=True)
psapi=C.WinDLL('psapi',use_last_error=True)
callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
kernel.GetProcessTimes.argtypes=[W.HANDLE,*([C.POINTER(W.FILETIME)]*4)]
kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
kernel.CloseHandle.argtypes=[W.HANDLE]
user.EnumWindows.argtypes=[callback,W.LPARAM]
user.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
user.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];user.GetWindowLongPtrW.restype=C.c_ssize_t
user.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t];user.SetWindowLongPtrW.restype=C.c_ssize_t


class Memory(C.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(name,C.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]


psapi.GetProcessMemoryInfo.argtypes=[W.HANDLE,C.POINTER(Memory),W.DWORD]
handle=None
pid=None


@callback
def find(hwnd,unused):
    global handle,pid
    name=C.create_unicode_buffer(128);user.GetClassNameW(hwnd,name,len(name))
    if name.value != 'CitlaliDesktopPetWindow_20261014':return True
    candidate=W.DWORD();user.GetWindowThreadProcessId(hwnd,C.byref(candidate))
    opened=kernel.OpenProcess(0x0400|0x0010,False,candidate.value)
    if not opened:return True
    path=C.create_unicode_buffer(32768);size=W.DWORD(len(path))
    if kernel.QueryFullProcessImageNameW(opened,0,path,C.byref(size)) and Path(path.value).resolve() == exe:
        # Keep the visible renderer representative while excluding manual
        # menu/drag input from this automated CPU sample only.
        user.SetWindowLongPtrW(hwnd,-20,user.GetWindowLongPtrW(hwnd,-20) | 0x20 | 0x08000000)
        handle,pid=opened,candidate.value
        return False
    kernel.CloseHandle(opened)
    return True


process=subprocess.Popen([str(exe),'--qa-seconds','45','--qa-scale',str(args.scale)],
    cwd=exe.parent,creationflags=subprocess.CREATE_NO_WINDOW)
started=time.perf_counter()
samples=[]
try:
    while process.poll() is None:
        if time.perf_counter()-started > 85:raise RuntimeError('CPU benchmark timed out')
        if handle is None:user.EnumWindows(find,0)
        if handle:
            creation,exit_time,kernel_time,user_time=[W.FILETIME() for _ in range(4)]
            if kernel.GetProcessTimes(handle,C.byref(creation),C.byref(exit_time),C.byref(kernel_time),C.byref(user_time)):
                cpu=sum((v.dwHighDateTime << 32)+v.dwLowDateTime for v in (kernel_time,user_time))/1e7
                memory=Memory();memory.cb=C.sizeof(memory)
                psapi.GetProcessMemoryInfo(handle,C.byref(memory),C.sizeof(memory))
                samples.append((time.perf_counter(),cpu,memory.WorkingSetSize,memory.PrivateUsage))
        time.sleep(.1)
    assert process.returncode == 0 and len(samples)>100
finally:
    if handle:kernel.CloseHandle(handle)
    if process.poll() is None:process.terminate();process.wait()
    if saved_settings is None:settings.unlink(missing_ok=True)
    else:settings.write_bytes(saved_settings)
raw=json.loads((exe.parent/'work/playback-qa.json').read_text(encoding='utf-8'))
draws=raw['draws'];times=[row[2] for row in draws]
segments=[]
for row in draws:
    if not segments or segments[-1][0] != row[0]:segments.append([row[0],row[2],row[2]])
    else:segments[-1][2]=row[2]
report={'scale':args.scale,'logical_processors':os.cpu_count(),'exe_bytes':exe.stat().st_size,
    'settings_sha256':hashlib.sha256(measurement_settings).hexdigest(),
    'automated_window_click_through':True,'actions':{}}
for name,start,end in segments:
    measurements=[(b[0]-a[0],b[1]-a[1]) for a,b in zip(samples,samples[1:])
        if a[0]>start+.75 and b[0]<end-.25 and a[0]>times[0]+3]
    if not measurements:continue
    elapsed=sum(row[0] for row in measurements);cpu=sum(row[1] for row in measurements)
    selected=[row for row in draws if row[0] == name and start+.75 < row[2] < end-.25]
    report['actions'][name]={'measured_seconds':elapsed,'cpu_seconds':cpu,
        'one_core_percent':100*cpu/elapsed,'task_manager_percent':100*cpu/elapsed/os.cpu_count(),
        'rendered_fps':(len(selected)-1)/(selected[-1][2]-selected[0][2])}
assert set(report['actions']) == {'standing','drinking','reading'}
report.update(peak_working_mib=max(row[2] for row in samples)/1024**2,
    peak_private_mib=max(row[3] for row in samples)/1024**2,
    peak_cache_bytes=raw['peak_cache_bytes'],peak_cache_frames=raw['peak_cache_frames'])
report['loop_cache_peak_bytes']=raw.get('loop_cache_peak_bytes',0)
assert report['loop_cache_peak_bytes'] <= 8*1024**2
assert raw['peak_cache_frames'] <= 12 and raw['peak_cache_bytes'] <= 24*1024**2
if args.label == 'after':
    before=json.loads((ROOT/'work/cpu-before.json').read_text(encoding='utf-8'))
    assert report['settings_sha256'] == before['settings_sha256'] and args.scale == before['scale']
    for name,row in report['actions'].items():
        row['cpu_reduction_percent']=100*(1-row['one_core_percent']/before['actions'][name]['one_core_percent'])
(ROOT/f'work/cpu-{args.label}.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
if args.label == 'after':
    assert all(row['rendered_fps']>57 for row in report['actions'].values())
    assert all(row['cpu_reduction_percent']>0 for row in report['actions'].values()),'An action did not improve'
