from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent/'sources'/'standing-qa'
cap=cv2.VideoCapture(r'E:\OBS\video\2026-10-14 21-04-51.mp4')
cap.set(cv2.CAP_PROP_POS_FRAMES,985);_,bgr=cap.read()
rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
for name,box in [('ribbons',(1050,800,1550,1080)),('soles',(1120,1200,1460,1310))]:
    x1,y1,x2,y2=box
    tile=Image.fromarray(rgb[y1:y2,x1:x2]).resize(((x2-x1)*3,(y2-y1)*3))
    draw=ImageDraw.Draw(tile)
    for x in range(x1,x2,25):
        draw.line(((x-x1)*3,0,(x-x1)*3,tile.height),fill='#ffae32',width=1)
        draw.text(((x-x1)*3+2,2),str(x),fill='black')
    for y in range(y1,y2,10 if name=='soles' else 25):
        draw.line((0,(y-y1)*3,tile.width,(y-y1)*3),fill='#ffae32',width=1)
        draw.text((2,(y-y1)*3+2),str(y),fill='black')
    tile.save(root/(name+'-grid.png'))
hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
for x in [1180,1190,1200,1210,1220,1230,1240,1250,1260,1340,1350,1360,1370,1380,1390,1400]:
    valid=(gray[1225:1295,x]<160)&(~((hsv[1225:1295,x,0]>=77)&(hsv[1225:1295,x,0]<=108)&(hsv[1225:1295,x,1]>35)))
    yy=np.flatnonzero(valid)+1225
    print(x,yy.tolist())
