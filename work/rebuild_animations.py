"""Rebuild original video pixels with completed props and smooth loop bridges."""
from pathlib import Path
import importlib.util
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageSequence

ROOT=Path(__file__).resolve().parent
SOURCE=Path(r'C:\Users\Lightw\Documents\Codex\2026-10-14\ni\work')
STAGE=ROOT/'repaired-assets'
STAGE.mkdir(exist_ok=True)
cv2.setNumThreads(2)
spec=importlib.util.spec_from_file_location('original_extract',SOURCE/'extract_pet.py')
original=importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
CANVAS=(400,420)

def decode(filename,crop):
    frames=[]; durations=[]
    with Image.open(SOURCE/filename) as im:
        for frame in ImageSequence.Iterator(im):
            frames.append(np.array(frame.convert('RGB').crop(crop)))
            durations.append(int(frame.info.get('duration',33)))
    return frames,durations

def finish_prop(rgb,mask,donor,blend_height=14):
    h,w=rgb.shape[:2]
    output=donor.copy()
    alpha=mask.astype(np.float32)
    output[:h,:,:3]=rgb
    output[:h,:,3]=(alpha*255).astype(np.uint8)
    # Completion is restricted to the bottom strip and its new lower contour.
    # Character RGB and the rest of its silhouette stay in the original video.
    for y in range(h-blend_height,h):
        t=(y-(h-blend_height))/(blend_height-1)
        da=donor[y,:,3].astype(np.float32)/255
        overlap=(alpha[y]>.5)&(da>.5)
        output[y,overlap,:3]=np.rint(rgb[y,overlap]*(1-t)+donor[y,overlap,:3]*t)
        uncovered=(alpha[y]<.5)&(da>.01)
        output[y,uncovered,:3]=donor[y,uncovered,:3]
        output[y,:,3]=np.rint(np.maximum(alpha[y],da*t)*255)
    output[output[:,:,3]<2]=0
    return output

def place(frames,scale):
    boxes=[Image.fromarray(f).getbbox() for f in frames]
    box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    scale=min(scale,(CANVAS[0]-32)/(box[2]-box[0]),(CANVAS[1]-32)/(box[3]-box[1]))
    size=(round((box[2]-box[0])*scale),round((box[3]-box[1])*scale))
    pos=((CANVAS[0]-size[0])//2,CANVAS[1]-size[1]-18)
    result=[]
    for f in frames:
        canvas=Image.new('RGBA',CANVAS)
        canvas.alpha_composite(Image.fromarray(f).crop(box).resize(size,Image.Resampling.LANCZOS),pos)
        result.append(np.asarray(canvas).copy())
    return result,box,scale

def flow_image(rgba):
    a=rgba[:,:,3:4].astype(np.float32)/255
    return cv2.cvtColor(np.uint8(rgba[:,:,:3]*a+64*(1-a)),cv2.COLOR_RGB2GRAY)

def flow_pair(a,b):
    ga,gb=flow_image(a),flow_image(b)
    f=cv2.calcOpticalFlowFarneback(ga,gb,None,.5,4,21,4,7,1.5,0)
    g=cv2.calcOpticalFlowFarneback(gb,ga,None,.5,4,21,4,7,1.5,0)
    return f,g

YY,XX=np.mgrid[:CANVAS[1],:CANVAS[0]].astype(np.float32)

def premult(rgba):
    a=rgba[:,:,3:4].astype(np.float32)/255
    return np.concatenate([rgba[:,:,:3].astype(np.float32)*a,a*255],axis=2)

def unpremult(p):
    alpha=p[:,:,3:4]
    rgb=np.divide(p[:,:,:3]*255,alpha,out=np.zeros_like(p[:,:,:3]),where=alpha>1)
    out=np.uint8(np.clip(np.concatenate([rgb,alpha],axis=2),0,255)+.5)
    out[out[:,:,3]<3]=0
    return out

def interpolate(a,b,f,g,t):
    if t<=.0001:return a.copy()
    if t>=.9999:return b.copy()
    pa,pb=premult(a),premult(b)
    wa=cv2.remap(pa,XX-f[:,:,0]*t,YY-f[:,:,1]*t,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    wb=cv2.remap(pb,XX-g[:,:,0]*(1-t),YY-g[:,:,1]*(1-t),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    return unpremult(wa*(1-t)+wb*t)

def smooth_loop(frames,durations,bridge_ms):
    # Small motion-compensated temporal filter reduces GIF palette flicker.
    fields=[flow_pair(a,b) for a,b in zip(frames,frames[1:])]
    cleaned=[]
    for i,frame in enumerate(frames):
        samples=[premult(frame)]
        if i:
            backwards=fields[i-1][1]
            samples.append(cv2.remap(premult(frames[i-1]),XX+backwards[:,:,0],YY+backwards[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT))
        if i+1<len(frames):
            forwards=fields[i][0]
            samples.append(cv2.remap(premult(frames[i+1]),XX+forwards[:,:,0],YY+forwards[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT))
        # Keep alpha geometry exact; filter colors gently in solid regions.
        p=premult(frame)
        avg=np.mean(samples,axis=0)
        solid=(p[:,:,3]>230)&(avg[:,:,3]>230)
        p[solid,:3]=p[solid,:3]*.55+avg[solid,:3]*.45
        cleaned.append(unpremult(p))
    seam_flow=flow_pair(cleaned[-1],cleaned[0])
    endpoints=np.r_[0,np.cumsum(durations[:-1])]
    end=float(endpoints[-1])
    count=round((end+bridge_ms)/1000*60)
    total=round(count*1000/60)
    bridge=total-end
    samples=[]
    for k in range(count):
        timestamp=k*total/count
        if timestamp<end:
            j=min(int(np.searchsorted(endpoints,timestamp,side='right')-1),len(cleaned)-2)
            t=(timestamp-endpoints[j])/(endpoints[j+1]-endpoints[j])
            sample=interpolate(cleaned[j],cleaned[j+1],*fields[j],float(t))
        else:
            t=(timestamp-end)/bridge
            sample=interpolate(cleaned[-1],cleaned[0],*seam_flow,float(t))
        samples.append(Image.fromarray(sample))
    times=[round((i+1)*total/count)-round(i*total/count) for i in range(count)]
    return samples,times

def export(name,frames,durations,scale,bridge,completion):
    placed,box,scale=place(frames,scale)
    smooth,times=smooth_loop(placed,durations,bridge)
    file=f'{name}-v2.webp'
    smooth[0].save(STAGE/file,save_all=True,append_images=smooth[1:],duration=times,loop=0,lossless=True,method=4)
    preview=Image.new('RGB',(CANVAS[0]*5,CANVAS[1]),(40,43,53))
    for j,index in enumerate([0,len(smooth)//4,len(smooth)//2,3*len(smooth)//4,len(smooth)-1]):
        bg=Image.new('RGBA',CANVAS,(40,43,53,255));bg.alpha_composite(smooth[index])
        preview.paste(bg.convert('RGB'),(j*CANVAS[0],0))
    preview.save(ROOT/f'{name}-repaired-qa.jpg',quality=94)
    first=np.asarray(smooth[0],dtype=np.float32);last=np.asarray(smooth[-1],dtype=np.float32)
    diffs=[float(np.abs(np.asarray(b,dtype=np.float32)-np.asarray(a,dtype=np.float32)).mean()) for a,b in zip(smooth,smooth[1:])]
    metrics={'seam_difference':float(np.abs(last-first).mean()),'median_frame_difference':float(np.median(diffs)),'max_frame_difference':float(max(diffs))}
    result={'file':file,'frames':len(smooth),'duration_ms':sum(times),'fps':60,'source_bbox':list(map(int,box)),'scale':scale,'completed_prop':completion,'loop_bridge_ms':round(bridge),'metrics':metrics}
    print(name,result,flush=True)
    return result

def run():
    items={}
    filename='4c3cff02911fae381805795a52169bfa_7408938001258415469.gif'
    rgb,times=decode(filename,(67,307,344,617))
    frames=[]
    for im in rgb:
        mask=original.cyan_matte(im)
        # The showcase has a floor reflection under the actual shoe soles.
        mask[298:]=0
        # Keep a small margin around the matte; do not crop alpha's feather.
        alpha=np.uint8(np.clip(cv2.GaussianBlur(mask.astype(np.float32),(3,3),.45)*255,0,255))
        rgba=np.dstack([im,alpha]);rgba[alpha<3]=0
        frames.append(rgba)
    items['standing']=export('standing',frames,times,1.1,750,False)
    rgb,times=decode(filename,(67,39,627,294))
    donor=np.array(Image.open(ROOT/'reading-complete-reference.png').convert('RGBA'))
    frames=[finish_prop(im,original.cyan_matte(im),donor) for im in rgb]
    items['reading']=export('reading',frames,times,.76,850,True)
    rgb,times=decode('282708336d95fc60df095ac812090de8_3432360643612152874.gif',(67,123,628,667))
    donor=np.array(Image.open(ROOT/'drinking-complete-reference.png').convert('RGBA'))
    # Preserve the already reviewed character mask, restore the support prop.
    # Track the full silhouette including pillow with a fresh initial mask.
    initial=np.array(Image.open(SOURCE/'drink-mask-initial.png'))>100
    initial=initial[123:667,67:628].astype(np.float32)
    pillow=donor[:len(initial),:,3].astype(np.float32)/255
    shape=np.maximum(initial,pillow)
    # The former character-only matte discarded the blue cloth and rear lobe
    # of the support cushion, leaving the knees floating above the pillow.
    support=np.zeros_like(initial,dtype=np.uint8)
    cv2.fillPoly(support,[np.array([[145,395],[137,423],[133,454],[100,459],[87,467],[85,475],[105,480],[448,480],[461,470],[455,463],[440,456],[420,452],[410,415],[397,395]],np.int32)],1)
    shape=np.maximum(shape,support)
    previous=cv2.cvtColor(rgb[0],cv2.COLOR_RGB2GRAY)
    h,w=shape.shape
    yy,xx=np.mgrid[:h,:w].astype(np.float32)
    frames=[]
    for i,im in enumerate(rgb):
        gray=cv2.cvtColor(im,cv2.COLOR_RGB2GRAY)
        if i:
            flow=cv2.calcOpticalFlowFarneback(gray,previous,None,.5,4,21,4,7,1.5,0)
            shape=cv2.remap(shape,xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        mask=(shape>.5).astype(np.uint8)
        # Refine only a narrow edge band to retain sleeves, hair and stitches.
        labels=np.full((h,w),cv2.GC_BGD,np.uint8)
        outer=cv2.dilate(mask,np.ones((5,5),np.uint8))
        inner=cv2.erode(mask,np.ones((5,5),np.uint8))
        labels[outer>0]=cv2.GC_PR_BGD
        labels[mask>0]=cv2.GC_PR_FGD
        labels[inner>0]=cv2.GC_FGD
        cv2.grabCut(im,labels,None,np.zeros((1,65)),np.zeros((1,65)),1,cv2.GC_INIT_WITH_MASK)
        refined=((labels==1)|(labels==3)).astype(np.uint8)
        frames.append(finish_prop(im,refined,donor))
        previous=gray
        if i%25==0:print('drinking mask',i,flush=True)
    items['drinking']=export('drinking',frames,times,.52,900,True)
    manifest={'version':2,'canvas':list(CANVAS),'animations':items,'source':'https://www.hoyolab.com/article/45557004','coverage':'Original official animation excerpts with optically interpolated 60 fps loop bridges. Missing lower pillow contours completed from image_gen references; character pixels remain from the source footage.'}
    (STAGE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':run()
