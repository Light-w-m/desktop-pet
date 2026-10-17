"""Verify source conversion, embedded ICO and every Windows icon resource."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe',type=Path,default=ROOT/'work/dist/CitlaliDesktopPet.exe')
args=parser.parse_args()
exe=args.exe.resolve()
icon=(ROOT/'assets/app.ico').read_bytes()
image=Image.open(ROOT/'assets/app-icon-source.jpg').convert('RGBA')
decoded=Image.open(io.BytesIO(icon))
assert set(decoded.ico.sizes()) == {(n,n) for n in (16,24,32,48,64,128,256)}
for size in decoded.ico.sizes():
    assert decoded.ico.getimage(size).convert('RGBA').tobytes() == image.resize(size,Image.Resampling.LANCZOS).tobytes()
archive=CArchiveReader(str(exe))
names={name.replace('\\','/'):name for name in archive.toc}
assert archive.extract(names['assets/app.ico']) == icon
kernel=C.WinDLL('kernel32',use_last_error=True)
kernel.LoadLibraryExW.argtypes=[W.LPCWSTR,W.HANDLE,W.DWORD];kernel.LoadLibraryExW.restype=W.HMODULE
kernel.FindResourceW.argtypes=[W.HMODULE,C.c_void_p,C.c_void_p];kernel.FindResourceW.restype=W.HANDLE
kernel.SizeofResource.argtypes=[W.HMODULE,W.HANDLE];kernel.SizeofResource.restype=W.DWORD
kernel.LoadResource.argtypes=[W.HMODULE,W.HANDLE];kernel.LoadResource.restype=W.HANDLE
kernel.LockResource.argtypes=[W.HANDLE];kernel.LockResource.restype=C.c_void_p
kernel.FreeLibrary.argtypes=[W.HMODULE]
module=kernel.LoadLibraryExW(str(exe),None,0x2 | 0x20)
if not module:raise C.WinError(C.get_last_error())
def resource(kind,number):
    found=kernel.FindResourceW(module,C.c_void_p(number),C.c_void_p(kind))
    if not found:raise C.WinError(C.get_last_error())
    return C.string_at(kernel.LockResource(kernel.LoadResource(module,found)),kernel.SizeofResource(module,found))
try:
    group=resource(14,1)
    count=struct.unpack_from('<H',group,4)[0]
    assert count == struct.unpack_from('<H',icon,4)[0] == 7
    sizes=[]
    for number in range(count):
        expected=struct.unpack_from('<BBBBHHII',icon,6+16*number)
        actual=struct.unpack_from('<BBBBHHIH',group,6+14*number)
        assert actual[:7] == expected[:7]
        assert resource(3,actual[-1]) == icon[expected[-1]:expected[-1]+expected[-2]]
        sizes.append(expected[0] or 256)
finally:kernel.FreeLibrary(module)
report={'source_image_preserved':True,'all_resolutions_match_source':True,
    'embedded_runtime_ico_matches':True,'windows_exe_resources_match':True,'sizes':sizes,
    'icon_sha256':hashlib.sha256(icon).hexdigest()}
(ROOT/'work/app-icon-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
