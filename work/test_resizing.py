"""Check sampling phase, extreme canvas edges and all user-selectable sizes."""
from pathlib import Path
import random
import sys

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from frame_stream import resize_native,pack_frame

randomizer=random.Random(691)
canvas=(840,720)
boxes=((0,0,70,80),(820,700,840,720),(0,160,840,200),
       (250,0,270,720),(323,97,565,665),(113,52,711,705))
scales=(.6,.7,.8,.9,1,1.1,1.2,1.3,1.4,1.5,.613,1.417)
for box in boxes:
    width,height=box[2]-box[0],box[3]-box[1]
    pixels=randomizer.randbytes(width*height*4)
    full=Image.new('RGBA',canvas)
    full.paste(Image.frombytes('RGBA',(width,height),pixels),box[:2])
    for scale in scales:
        size=(round(560*scale),round(480*scale))
        assert resize_native(pixels,box,canvas,size) == pack_frame(full.resize(size,Image.Resampling.LANCZOS)),(box,size)
print('72 resampling cases match full-canvas Lanczos exactly, including canvas edges and irregular scales.')
