"""Copy premultiplied BGRA tiles into a mapped Win32 bitmap in native code."""
import ctypes as C

from PIL import Image


class PixelSurface:
    def __init__(self, address, size):
        self.size=size
        self.buffer=(C.c_ubyte*(size[0]*size[1]*4)).from_address(address)
        # Channel names are immaterial here: this is a byte copy, not blending.
        self.image=Image.frombuffer('RGBA',size,self.buffer,'raw','RGBA',0,1)
        self.image.readonly=0

    def paint(self, frame):
        self.image.paste(0,(0,0,*self.size))
        tile=Image.frombytes('RGBA',frame['size'],frame['pixels'])
        self.image.paste(tile,frame['offset'])

    def close(self):
        self.image.close()
        self.image=self.buffer=None
