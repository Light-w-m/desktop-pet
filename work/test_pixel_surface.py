"""Compare the mapped drawing buffer with the former row-copy renderer."""
import ctypes as C
from pathlib import Path
import random
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'src'))
from citlali_pet.ui.pixel_surface import PixelSurface

randomizer=random.Random(471)
for size in ((336,288),(560,480),(728,624),(840,720)):
    actual=(C.c_ubyte*(size[0]*size[1]*4))()
    expected=(C.c_ubyte*len(actual))()
    surface=PixelSurface(C.addressof(actual),size)
    for _ in range(15):
        width,height=randomizer.randrange(1,size[0]),randomizer.randrange(1,size[1])
        x,y=randomizer.randrange(size[0]-width),randomizer.randrange(size[1]-height)
        pixels=randomizer.randbytes(width*height*4)
        C.memset(expected,0,len(expected))
        source=C.cast(C.c_char_p(pixels),C.c_void_p).value
        for row in range(height):
            C.memmove(C.addressof(expected)+((y+row)*size[0]+x)*4,source+row*width*4,width*4)
        surface.paint({'pixels':pixels,'offset':(x,y),'size':(width,height)})
        assert bytes(actual) == bytes(expected),(size,width,height)
    surface.close()
print('60 successive drawing buffers match exactly, including transparent pixels and cleared old bounds.')
