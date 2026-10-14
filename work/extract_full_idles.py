"""Extract complete character-and-pillow sequences from a public game capture."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image,ImageSequence

ROOT=Path(__file__).resolve().parent
STAGE=ROOT/'repaired-assets'
STAGE.mkdir(exist_ok=True)
CANVAS=(400,420)
SOURCE_URL='https://www.bilibili.com/video/BV1pUTo6HE8X/'
CROP=(300,75,925,645)
cv2.setNumThreads(2)

def matte(rgb):
    r,g,b=rgb.astype(np.int16).transpose(2,0,1)
    background=(g>r+9)&(b>r+16)&(b<g+77)
    foreground=(~background).astype(np.uint8)
    # Exclude the mirror reflection below the actual shoe soles. The complete
    # pillows float above this height; none of their edges are cropped.
    foreground[638-CROP[1]:]=0
    n,labels,stats,centers=cv2.connectedComponentsWithStats(foreground,8)
    if n<2:raise ValueError('Missing foreground')
    primary=1+np.argmax(stats[1:,cv2.CC_STAT_AREA])
    selected=(labels==primary)
    px,py,pw,ph,_=stats[primary]
    # Retain the detached blue companion; omit detached white menu sparkles.
    for k in range(1,n):
        x,y,w,h,area=stats[k]
        cx,cy=centers[k]
        if k==primary or not 80<=area<=6000:continue
        if x<6 or y<6 or x+w>=rgb.shape[1]-6 or y+h>=rgb.shape[0]-6:continue
        if w>140 or h>180 or cy<50 or cy>py+ph+12:continue
        if cx<px-120 or cx>px+pw+60:continue
        region=labels==k
        dark_blue=(b>r+25)&(b>g+15)&(r<145)&(g<155)
        if np.mean(dark_blue[region])>.16:
            selected|=region
    mask=cv2.morphologyEx(selected.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    # Blue-gray boot shading and the pillow band can match the cyan key.
    # Restore only small enclosed regions; large gaps and exterior background
    # remain transparent. Restored RGB always comes from the original video.
    count,hole_labels,hole_stats,_=cv2.connectedComponentsWithStats(1-mask,8)
    holes=[]
    for k in range(1,count):
        x,y,w,h,area=hole_stats[k]
        if area<=1200 and x>0 and y>0 and x+w<mask.shape[1] and y+h<mask.shape[0]:holes.append(k)
    if holes:mask[np.isin(hole_labels,holes)]=1
    alpha=np.uint8(np.clip(cv2.GaussianBlur(mask.astype(np.float32),(3,3),.5)*255,0,255))
    alpha[alpha<4]=0
    output=np.dstack((rgb,alpha))
    output[alpha==0]=0
    return output

def decode(start,end):
    cap=cv2.VideoCapture(str(ROOT/'sources'/'full-idles.mp4'))
    fps=cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES,round(start*fps))
    frames=[]
    for i in range(round((end-start)*fps)):
        ok,frame=cap.read()
        if not ok:raise ValueError('Source decode ended early')
        rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)[CROP[1]:CROP[3],CROP[0]:CROP[2]]
        frames.append(matte(rgb))
    cap.release()
    return frames,1000/fps

def pose_layout(clips):
    boxes=[Image.fromarray(f).getbbox() for frames,_ in clips.values() for f in frames]
    box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    scale=min((CANVAS[0]-36)/(box[2]-box[0]),(CANVAS[1]-36)/(box[3]-box[1]),.80)
    size=(round((box[2]-box[0])*scale),round((box[3]-box[1])*scale))
    pos=((CANVAS[0]-size[0])//2,CANVAS[1]-size[1]-18)
    output={}
    for name,(frames,duration) in clips.items():
        canvases=[]
        for frame in frames:
            image=Image.new('RGBA',CANVAS)
            image.alpha_composite(Image.fromarray(frame).crop(box).resize(size,Image.Resampling.LANCZOS),pos)
            canvases.append(np.asarray(image).copy())
        output[name]=(canvases,duration)
    return output,box,scale

YY,XX=np.mgrid[:CANVAS[1],:CANVAS[0]].astype(np.float32)

def visual(rgba):
    a=rgba[:,:,3:4].astype(np.float32)/255
    return cv2.cvtColor(np.uint8(rgba[:,:,:3]*a+64*(1-a)),cv2.COLOR_RGB2GRAY)

def premult(rgba):
    a=rgba[:,:,3:4].astype(np.float32)/255
    return np.concatenate((rgba[:,:,:3].astype(np.float32)*a,a*255),axis=2)

def blend(a,b,t):
    if t<.0001:return a
    if t>.9999:return b
    f=cv2.calcOpticalFlowFarneback(visual(a),visual(b),None,.5,3,19,3,7,1.5,0)
    g=cv2.calcOpticalFlowFarneback(visual(b),visual(a),None,.5,3,19,3,7,1.5,0)
    wa=cv2.remap(premult(a),XX-f[:,:,0]*t,YY-f[:,:,1]*t,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    wb=cv2.remap(premult(b),XX-g[:,:,0]*(1-t),YY-g[:,:,1]*(1-t),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    p=wa*(1-t)+wb*t
    alpha=p[:,:,3:4]
    rgb=np.divide(p[:,:,:3]*255,alpha,out=np.zeros_like(p[:,:,:3]),where=alpha>1)
    result=np.uint8(np.clip(np.concatenate((rgb,alpha),axis=2),0,255)+.5)
    result[result[:,:,3]<3]=0
    return result

def export(name,frames,duration,source_range,box,scale):
    # Source captures are native 30 fps. Interpolate each adjacent pair once,
    # retaining original poses and their original relative object positions.
    output=[]
    for i,frame in enumerate(frames):
        output.append(Image.fromarray(frame))
        if i+1<len(frames):output.append(Image.fromarray(blend(frame,frames[i+1],.5)))
        if i%120==0:print(name,'interpolate',i,'/',len(frames),flush=True)
    bridge_frames=36
    for k in range(1,bridge_frames+1):
        output.append(Image.fromarray(blend(frames[-1],frames[0],k/(bridge_frames+1))))
    times=[round((i+1)*1000/60)-round(i*1000/60) for i in range(len(output))]
    filename=f'{name}-full.webp'
    output[0].save(STAGE/filename,save_all=True,append_images=output[1:],duration=times,loop=0,lossless=False,quality=92,method=2)
    # Quarter-clip sheets include pose starts, complete props, and pose ends.
    sheet=Image.new('RGB',(CANVAS[0]*5,CANVAS[1]),(40,43,53))
    for column,index in enumerate([0,len(output)//4,len(output)//2,3*len(output)//4,len(output)-1]):
        bg=Image.new('RGBA',CANVAS,(40,43,53,255));bg.alpha_composite(output[index])
        sheet.paste(bg.convert('RGB'),(column*CANVAS[0],0))
    sheet.save(ROOT/f'{name}-full-qa.jpg',quality=95)
    result={'file':filename,'frames':len(output),'duration_ms':sum(times),'fps':60,'source_range_seconds':source_range,'source_bbox':list(map(int,box)),'scale':scale,'completed_prop':False,'full_character_and_pillow':True,'native_pose_transitions':name!='standing','loop_bridge_ms':600}
    print(name,result,flush=True)
    return result

def main():
    ranges={'standing':[2.2,4.1],'reading':[4.1,17.8],'drinking':[20.7,38.1]}
    decoded={name:decode(*times) for name,times in ranges.items()}
    laid_out,box,scale=pose_layout(decoded)
    del decoded
    items={name:export(name,*laid_out[name],ranges[name],box,scale) for name in ranges}
    manifest={'version':3,'canvas':list(CANVAS),'animations':items,'source':SOURCE_URL,'coverage':'Complete character-and-pillow framing from an in-game outfit preview. Native pose starts and returns retained. Original character and pillow relative positions are preserved; no generated pillow completion or layer offsets.'}
    (STAGE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
