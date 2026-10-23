"""Track planted shoes and key costume ribbons from each current frame."""
import cv2
import numpy as np
from matte_obs import matte,CROP

FOOT_REGIONS=[
    ((1135,1150,1310,1310),[(1162,1225),(1177,1238),(1184,1253),(1193,1260),(1208,1263),(1225,1264),(1246,1263),(1264,1259),(1272,1254),(1281,1231)]),
    ((1290,1160,1480,1320),[(1322,1242),(1336,1260),(1345,1271),(1359,1276),(1376,1279),(1393,1280),(1408,1278),(1421,1276),(1429,1263),(1439,1242)]),
]
# Cover the full swing, including the pink fabric that leaves the old
# fixed optical-flow template. These are the costume tails beside the knees.
RIBBON_REPAIR_REGIONS=[(1000,870,1230,1015),(1340,870,1555,1015)]


def ribbon_alpha(tile):
    """Use the current frame's fabric, never a warped sky-coloured template."""
    r,g,b=np.moveaxis(tile.astype('int16'),2,0)
    sky=(g>r+7)&(b>r+12)
    seed=(~sky).astype('uint8')
    count,labels,stats,_=cv2.connectedComponentsWithStats(seed,8)
    pink=(r>g+12)&(b>g+6)&(r>100)
    mask=np.zeros(seed.shape,'uint8')
    for label in range(1,count):
        x,y,w,h,area=stats[label]
        part=labels==label
        # Retain connected costume/leg contours and detached pink fabric;
        # exclude isolated white stars from the recorded background.
        if area>=20 and (y<5 or (pink&part).sum()>20):mask[part]=1
    alpha=cv2.GaussianBlur(mask.astype('float32')*255,(3,3),.45)
    alpha[sky]=0
    return np.uint8(alpha+.5)

def crop_rect(rgb,rect):
    x1,y1,x2,y2=rect
    return rgb[y1:y2,x1:x2]

def fill_holes(mask):
    flood=np.pad(mask,1)
    cv2.floodFill(flood,None,(0,0),1)
    return mask|(1-flood[1:-1,1:-1])

class StandingMatte:
    def __init__(self,reference_rgb):
        x1,y1,x2,y2=CROP
        self.parts=[]
        for rect,curve in FOOT_REGIONS:
            tile=crop_rect(reference_rgb,rect)
            hsv=cv2.cvtColor(tile,cv2.COLOR_RGB2HSV)
            background=(hsv[:,:,0]>=77)&(hsv[:,:,0]<=108)&(hsv[:,:,1]>35)
            mask=(~background).astype('uint8')
            cx,cy,rx,ry=rect
            xs=np.arange(cx,rx)
            points=np.array(curve,dtype='float32')
            bottom=np.interp(xs,points[:,0],points[:,1],left=cy-1,right=cy-1)+1
            # Only the lower slipper needs the curved sole boundary. The
            # upper boot joins the leg and retains its native outline.
            yy=np.arange(cy,ry)[:,None]
            mask[(yy>bottom)&(yy>1220)]=0
            count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
            mask=(labels==1+np.argmax(stats[1:,cv2.CC_STAT_AREA])).astype('uint8')
            mask=fill_holes(mask)
            alpha=cv2.GaussianBlur(mask.astype('float32')*255,(3,3),.5)
            self.parts.append((rect,cv2.cvtColor(tile,cv2.COLOR_RGB2GRAY),alpha,True))

    def apply(self,rgb):
        x1,y1,x2,y2=CROP
        original=rgb[y1:y2,x1:x2]
        alpha=matte(original)[:,:,3].astype('float32')
        for rect,reference,template,rigid in self.parts:
            cx,cy,rx,ry=rect
            current=cv2.cvtColor(crop_rect(rgb,rect),cv2.COLOR_RGB2GRAY)
            flow=cv2.calcOpticalFlowFarneback(current,reference,None,.5,4,25,4,7,1.5,0)
            if rigid:
                core=cv2.erode((template>220).astype('uint8'),np.ones((7,7),'uint8'))>0
                offset=np.median(flow[core],axis=0)
                offset=np.clip(np.round(offset*4)/4,-40,40)
                flow[:]=offset
            else:
                flow=cv2.GaussianBlur(flow,(5,5),1)
                flow=np.clip(flow,-25,25)
            yy,xx=np.mgrid[:template.shape[0],:template.shape[1]].astype('float32')
            tracked=cv2.remap(template,xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            alpha[cy-y1:ry-y1,cx-x1:rx-x1]=tracked
        for rect in RIBBON_REPAIR_REGIONS:
            cx,cy,rx,ry=rect
            alpha[cy-y1:ry-y1,cx-x1:rx-x1]=ribbon_alpha(crop_rect(rgb,rect))
        # Isolated floor lights and reflections must never survive outside
        # either shoe, including the gap between the two planted feet.
        row_start=1220-y1
        foot_union=np.zeros_like(alpha[row_start:])
        for rect,_,_,rigid in self.parts:
            if not rigid:continue
            cx,cy,rx,ry=rect
            top=max(1220,cy)
            foot_union[top-1220:ry-1220,cx-x1:rx-x1]=alpha[top-y1:ry-y1,cx-x1:rx-x1]
        alpha[row_start:]=foot_union
        alpha=np.uint8(np.clip(alpha,0,255)+.5)
        alpha[alpha<5]=0
        result=np.dstack((original,alpha))
        result[alpha==0,:3]=0
        return result

def reference_from_video():
    cap=cv2.VideoCapture(r'E:\OBS\video\2026-10-14 21-04-51.mp4')
    cap.set(cv2.CAP_PROP_POS_FRAMES,985)
    ok,bgr=cap.read();cap.release()
    if not ok:raise RuntimeError('Standing reference is unavailable')
    return cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)

if __name__=='__main__':
    from pathlib import Path
    from PIL import Image
    from extract_obs import layout
    root=Path(__file__).resolve().parent/'sources'/'standing-qa'
    reference=reference_from_video()
    repair=StandingMatte(reference)
    cap=cv2.VideoCapture(r'E:\OBS\video\2026-10-14 21-04-51.mp4')
    sheet=Image.new('RGB',(840*3,720),'#252b3b')
    for column,index in enumerate([0,40,140]):
        cap.set(cv2.CAP_PROP_POS_FRAMES,945+index);_,bgr=cap.read()
        rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        rgba=repair.apply(rgb)
        Image.fromarray(rgba).save(root/('repaired-native-%s.png'%index))
        pose=layout(rgba)
        sheet.paste(pose,(column*840,0),pose)
    sheet.save(root/'repaired-contact.png')
