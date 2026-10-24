"""Prepare only a user-selected local image for the chat request."""
from dataclasses import dataclass
import ctypes as C
from ctypes import wintypes as W
from io import BytesIO
from pathlib import Path
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SOURCE_BYTES = 20*1024*1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 2048
MAX_IMAGE_BYTES = 2*1024*1024


class ImageError(ValueError):
    pass


@dataclass(frozen=True)
class ChatImage:
    name: str
    data: bytes
    mime: str
    width: int
    height: int

    def preview(self, bounds):
        with Image.open(BytesIO(self.data)) as image:
            image.thumbnail(bounds, Image.Resampling.LANCZOS)
            image = image.convert('RGB')
            return image.size, image.tobytes('raw', 'BGRX')


@dataclass(frozen=True)
class ImageMessage:
    text: str
    image: ChatImage


def load_image(path):
    path = Path(path)
    try:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ImageError('图片不能超过 20 MB，请选择较小的图片。')
        with path.open('rb') as source:
            data = source.read(MAX_SOURCE_BYTES+1)
        if len(data) > MAX_SOURCE_BYTES:
            raise ImageError('图片不能超过 20 MB，请选择较小的图片。')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
                    raise ImageError('请选择 PNG、JPG、WebP 或 GIF 图片。')
                if source.width*source.height > MAX_PIXELS:
                    raise ImageError('图片像素过大，请缩小后再选择。')
                source.seek(0)  # Animated formats send their first frame only.
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
                rgba = oriented.convert('RGBA')
                # Rebuild pixels on white; do not copy EXIF, GPS or PNG metadata.
                image = Image.new('RGB', rgba.size, 'white')
                image.paste(rgba, mask=rgba.getchannel('A'))
        output = BytesIO()
        image.save(output, 'PNG')
        mime = 'image/png'
        if output.tell() > MAX_IMAGE_BYTES:
            output = BytesIO()
            image.save(output, 'JPEG', quality=85, optimize=True)
            mime = 'image/jpeg'
        if output.tell() > MAX_IMAGE_BYTES:
            raise ImageError('图片压缩后仍过大，请缩小后再选择。')
        return ChatImage(path.name, output.getvalue(), mime, image.width, image.height)
    except ImageError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageError('无法读取这张图片，请检查文件或换一张图片。') from None


class OPENFILENAME(C.Structure):
    _fields_ = [('size',W.DWORD),('owner',W.HWND),('instance',W.HINSTANCE),
                ('filter',W.LPCWSTR),('custom_filter',W.LPWSTR),('max_custom',W.DWORD),
                ('filter_index',W.DWORD),('file',W.LPWSTR),('max_file',W.DWORD),
                ('file_title',W.LPWSTR),('max_title',W.DWORD),('initial_dir',W.LPCWSTR),
                ('title',W.LPCWSTR),('flags',W.DWORD),('file_offset',W.WORD),
                ('extension_offset',W.WORD),('default_extension',W.LPCWSTR),
                ('custom_data',C.c_ssize_t),('hook',C.c_void_p),('template',W.LPCWSTR),
                ('reserved',C.c_void_p),('reserved_flags',W.DWORD),('flags_ex',W.DWORD)]


def choose_image(owner):
    dialog = C.WinDLL('comdlg32', use_last_error=True)
    dialog.GetOpenFileNameW.argtypes, dialog.GetOpenFileNameW.restype = [C.POINTER(OPENFILENAME)], W.BOOL
    dialog.CommDlgExtendedError.restype = W.DWORD
    buffer = C.create_unicode_buffer(32768)
    spec = OPENFILENAME()
    spec.size, spec.owner = C.sizeof(spec), owner
    spec.filter = '图片 (PNG / JPG / WebP / GIF)\0*.png;*.jpg;*.jpeg;*.webp;*.gif\0\0'
    spec.file, spec.max_file = C.cast(buffer,W.LPWSTR), len(buffer)
    spec.title = '选择要识别的图片'
    spec.flags = 0x00080000 | 0x00001000 | 0x00000800 | 0x8 | 0x02000000
    if dialog.GetOpenFileNameW(C.byref(spec)):return buffer.value
    if dialog.CommDlgExtendedError():raise ImageError('图片选择窗口未能打开，请稍后重试。')
    return None


def paint_image(api, dc, preview, x, y):
    (width,height), pixels = preview
    api.signature(api.gdi,'StretchDIBits',C.c_int,W.HDC,*([C.c_int]*8),C.c_void_p,C.POINTER(api.BITMAPINFO),W.UINT,W.DWORD)
    info = api.BITMAPINFO()
    info.bmiHeader.biSize = C.sizeof(api.BITMAPINFOHEADER)
    info.bmiHeader.biWidth, info.bmiHeader.biHeight = width, -height
    info.bmiHeader.biPlanes, info.bmiHeader.biBitCount = 1, 32
    buffer = C.create_string_buffer(pixels)
    api.gdi.StretchDIBits(dc,x,y,width,height,0,0,width,height,buffer,C.byref(info),0,0x00CC0020)
