from pathlib import Path
import cv2
from PIL import Image,ImageDraw

root=Path(__file__).resolve().parent/'sources'/'standing-qa'
root.mkdir(parents=True,exist_ok=True)
source=cv2.VideoCapture(r'E:\OBS\video\2026-10-14 21-04-51.mp4')
sheet=Image.new('RGB',(1500,1350),'#252b3b')
draw=ImageDraw.Draw(sheet)
with Image.open(Path(__file__).resolve().parent.parent/'assets'/'standing-obs.webp') as asset:
    for column,index in enumerate([0,40,80,120,140]):
        source.set(cv2.CAP_PROP_POS_FRAMES,945+index)
        ok,bgr=source.read()
        rgb=Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
        rgb.crop((1050,300,1550,1310)).save(root/('source-%s.png'%index))
        asset.seek(index)
        rgba=asset.convert('RGBA')
        rgba.save(root/('sprite-%s.png'%index))
        bg=Image.new('RGBA',rgba.size,'#252b3b');bg.alpha_composite(rgba)
        # Source soles and sprite soles, then source/sprite ribbon regions.
        tiles=[rgb.crop((1110,1150,1430,1290)),bg.crop((340,600,545,700)),rgb.crop((1060,710,1530,1040)),bg.crop((305,330,590,540))]
        for row,tile in enumerate(tiles):
            tile.thumbnail((290,310),Image.Resampling.LANCZOS)
            sheet.paste(tile.convert('RGB'),(column*300,row*330+25))
        draw.text((column*300+10,5),str(index),fill='white')
sheet.save(root/'contact.png')
