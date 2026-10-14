"""Rebuild native 60 Hz lossless sprites from the user's local OBS clips."""
from pathlib import Path
import json
import subprocess
import tempfile
from collections import deque
import cv2
import numpy as np
from PIL import Image
from matte_obs import CROP, matte

ROOT=Path(__file__).resolve().parent
STAGE=ROOT/'repaired-assets'
CANVAS=(840,720)
BOX=(100,130,1070,1170)
SCALE=(600-36)/(BOX[2]-BOX[0])
AFFINE=np.float32([[SCALE,0,CANVAS[0]/2-SCALE*(BOX[0]+BOX[2])/2],[0,SCALE,630-22-SCALE*BOX[3]+80]])
SOURCES={
    'reading':(Path(r'E:\OBS\video\2026-10-14 21-04-10.mp4'),2.10,15.70),
    'drinking':(Path(r'E:\OBS\video\2026-10-14 21-04-51.mp4'),0.0,15.75),
    'standing':(Path(r'E:\OBS\video\2026-10-14 21-04-51.mp4'),15.75,18.30),
}

def layout(rgba):
    # Resize premultiplied pixels, avoiding a cyan fringe in transparent RGB.
    a=rgba[:,:,3:4].astype('float32')/255
    p=np.concatenate((rgba[:,:,:3].astype('float32')*a,a*255),axis=2)
    p=cv2.warpAffine(p,AFFINE,CANVAS,flags=cv2.INTER_AREA)
    alpha=p[:,:,3:4]
    rgb=np.divide(p[:,:,:3]*255,alpha,out=np.zeros_like(p[:,:,:3]),where=alpha>1)
    return Image.fromarray(np.uint8(np.clip(np.concatenate((rgb,alpha),axis=2),0,255)+.5))

def frames(name,standing_repair=None):
    if standing_repair is None:
        from standing_matte import StandingMatte,reference_from_video
        standing_repair=StandingMatte(reference_from_video())
    path,start,end=SOURCES[name]
    cap=cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES,round(start*60))
    for i in range(round((end-start)*60)):
        ok,bgr=cap.read()
        if not ok:raise RuntimeError('Missing source frame %s %s'%(name,i))
        x1,y1,x2,y2=CROP
        full_rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        if name=='standing' or i<12 or i>=round((end-start)*60)-12:
            rgba=standing_repair.apply(full_rgb)
        else:rgba=matte(full_rgb[y1:y2,x1:x2])
        yield layout(rgba)
        if i%60==0:print(name,i,'/',round((end-start)*60),flush=True)
    cap.release()

def mix(a,b,t):
    # Very short endpoint blend is only applied to nearly identical standing
    # poses, never to the seated/lying character or cushion geometry.
    a=np.array(a).astype('float32');b=np.array(b).astype('float32')
    aa=a[:,:,3:4]/255;ba=b[:,:,3:4]/255
    alpha=aa*(1-t)+ba*t
    p=a[:,:,:3]*aa*(1-t)+b[:,:,:3]*ba*t
    rgb=np.divide(p,alpha,out=np.zeros_like(p),where=alpha>0)
    return Image.fromarray(np.uint8(np.clip(np.concatenate((rgb,alpha*255),axis=2),0,255)+.5))

def main():
    STAGE.mkdir(exist_ok=True)
    from standing_matte import StandingMatte,reference_from_video
    standing_repair=StandingMatte(reference_from_video())
    canonical=next(frames('standing',standing_repair)).copy()
    items={}
    for name in ['standing','reading','drinking']:
        # A common endpoint eliminates switching seams. Both action recordings
        # include real standing starts and real returns, kept at native speed.
        bridge=12
        filename=name+'-obs.webp'
        path,start,end=SOURCES[name]
        count=round((end-start)*60)
        sheet=Image.new('RGB',(560*5,480),(30,33,44))
        samples={0:0,count//4:1,count//2:2,3*count//4:3,count-1:4}
        def sample(pose,index):
            if index in samples:
                pose=pose.resize((560,480),Image.Resampling.LANCZOS)
                sheet.paste(pose,(samples[index]*560,0),pose)
        # Stream into the encoder: no multi-gigabyte list of raw frames.
        with tempfile.TemporaryFile() as errors:
            process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgba','-s','840x720','-framerate','60','-i','pipe:0','-an','-c:v','libwebp_anim','-lossless','1','-compression_level','0','-loop','0',str(STAGE/filename)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
            tail=deque()
            for i,pose in enumerate(frames(name,standing_repair)):
                if i<bridge:pose=mix(canonical,pose,i/(bridge-1))
                tail.append((i,pose))
                if len(tail)>bridge:
                    index,ready=tail.popleft()
                    sample(ready,index)
                    process.stdin.write(ready.tobytes())
            for k,(index,pose) in enumerate(tail):
                ready=mix(pose,canonical,k/(bridge-1))
                sample(ready,index)
                process.stdin.write(ready.tobytes())
            process.stdin.close()
            result=process.wait()
            if result:
                errors.seek(0)
                raise RuntimeError(errors.read().decode('utf-8','replace'))
        with Image.open(STAGE/filename) as encoded:
            # The WebP encoder may coalesce identical frames; report actual
            # media timing rather than assuming one chunk per source frame.
            durations=[]
            for i in range(encoded.n_frames):
                encoded.seek(i);encoded.load();durations.append(encoded.info['duration'])
        items[name]={'file':filename,'frames':len(durations),'duration_ms':sum(durations),'fps':60,'source_range_seconds':[start,end],'source_file':path.name,'lossless':True,'native_frames':True,'full_character_and_pillow':True,'endpoint_blend_ms':200,'standing_contours_repaired':True}
        sheet.save(ROOT/(name+'-obs-qa.jpg'),quality=96)
    manifest={'version':5,'canvas':list(CANVAS),'display_canvas':[560,480],'animations':items,'coverage':'Complete native poses with shared standing endpoints, tracked shoe contours excluding floor reflection, and tracked ribbon knots. Original character and cushion proportions retained.'}
    (STAGE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Done',items,flush=True)

if __name__=='__main__':main()
