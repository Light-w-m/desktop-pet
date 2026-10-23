"""Remove the floor island between boots and finish on the exact idle frame."""
import hashlib
import json
from pathlib import Path
import sys
import zlib

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'work/sources/drag-deps'))
import cv2
import numpy as np
from PIL import Image,ImageDraw

FOLDER=ROOT/'assets/stomping'
LOCAL=ROOT/'local-media/stomp-handoff-fix-20261023'
HANDOFF_FRAMES=36
cv2.setNumThreads(3)


def native(stream,record):
    offset,length,x,y,X,Y=record
    stream.seek(offset)
    result=Image.new('RGBA',(840,720))
    result.paste(Image.frombytes('RGBA',(X-x,Y-y),zlib.decompress(stream.read(length))),(x,y))
    return np.asarray(result).copy()


def clear_floor_gap(rgba):
    """Keep each boot's bright fabric and outline; remove the dark floor island."""
    x,y,X,Y=350,595,570,688
    tile=rgba[y:Y,x:X];rgb=tile[:,:,:3]
    fabric=((rgb.min(axis=2)>100)&(rgb.max(axis=2)>155)&(tile[:,:,3]>180)).astype('uint8')
    fabric=cv2.morphologyEx(fabric,cv2.MORPH_CLOSE,np.ones((5,5),'uint8'))
    count,labels,stats,centres=cv2.connectedComponentsWithStats(fabric,8)
    choices=[i for i in range(1,count) if stats[i,cv2.CC_STAT_AREA]>170]
    if len(choices)<2:return rgba,0
    boots=sorted(sorted(choices,key=lambda i:stats[i,cv2.CC_STAT_AREA],reverse=True)[:2],key=lambda i:centres[i,0])
    left,right=[centres[i,0] for i in boots]
    if right-left<35:return rgba,0
    envelope=np.zeros(fabric.shape,'uint8')
    for label in boots:
        points=cv2.findNonZero((labels==label).astype('uint8'))
        cv2.fillConvexPoly(envelope,cv2.convexHull(points),1)
    envelope=cv2.dilate(envelope,np.ones((7,7),'uint8'))
    yy,xx=np.mgrid[:tile.shape[0],:tile.shape[1]]
    gap=(xx>left)&(xx<right)&(yy+y>620)&(envelope==0)&(rgb.max(axis=2)<155)
    removed=int(np.sum(gap&(tile[:,:,3]>10)))
    tile[gap]=0
    return rgba,removed


def premultiply(rgba):
    value=rgba.astype('float32');value[:,:,:3]*=value[:,:,3:4]/255
    return value


def straight(value):
    alpha=value[:,:,3:4]
    rgb=np.divide(value[:,:,:3]*255,alpha,out=np.zeros_like(value[:,:,:3]),where=alpha>.5)
    result=np.uint8(np.clip(np.concatenate((rgb,alpha),axis=2),0,255)+.5)
    result[result[:,:,3]==0,:3]=0
    return result


def morph(source,target,ratio,tracker,grid):
    if ratio<=0:return source
    if ratio>=1:return target.copy()
    a,b=premultiply(source),premultiply(target)
    ga,gb=(cv2.cvtColor(np.uint8(np.clip(v[:,:,:3],0,255)),cv2.COLOR_RGB2GRAY) for v in (a,b))
    forward=tracker.calc(ga,gb,None);backward=tracker.calc(gb,ga,None)
    forward=cv2.GaussianBlur(np.clip(forward,-35,35),(0,0),1)
    backward=cv2.GaussianBlur(np.clip(backward,-35,35),(0,0),1)
    yy,xx=grid
    wa=cv2.remap(a,xx-forward[:,:,0]*ratio,yy-forward[:,:,1]*ratio,cv2.INTER_LINEAR)
    wb=cv2.remap(b,xx-backward[:,:,0]*(1-ratio),yy-backward[:,:,1]*(1-ratio),cv2.INTER_LINEAR)
    return straight(wa*(1-ratio)+wb*ratio)


def encode(stream,image,display=False):
    box=image.getbbox();tile=np.asarray(image.crop(box)).copy()
    if display:
        tile[:,:,:3]=tile[:,:,:3].astype('uint16')*tile[:,:,3:4]//255
        tile=tile[:,:,[2,1,0,3]]
    data=zlib.compress(tile.tobytes(),3)
    record=[stream.tell(),len(data),*box];stream.write(data)
    return record


def repair():
    LOCAL.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((FOLDER/'source.json').read_text())
    reference=ROOT/'assets/standing-obs.webp';reference_sha=hashlib.sha256(reference.read_bytes()).hexdigest()
    if metadata.get('handoff_repair',{}).get('version')==1:
        assert metadata['handoff_repair']['reference_sha256']==reference_sha,'Rebuild the original stomp before changing its idle reference'
        print('Stomp handoff repair is up to date.',flush=True);return
    index=json.loads((FOLDER/'pet-frames.json').read_text());records=index['animations']['stomping']['frames']
    target=np.asarray(Image.open(reference).convert('RGBA'))
    count=len(records);start=count-HANDOFF_FRAMES
    tracker=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    grid=np.mgrid[:720,:840].astype('float32')
    new=[];removed=[];samples=[]
    temporary=FOLDER/'pet-frames.part.bin'
    with (FOLDER/index['data']).open('rb') as original,temporary.open('wb') as packed:
        for number,record in enumerate(records):
            rgba=native(original,record['native']);before=rgba.copy()
            rgba,pixels=clear_floor_gap(rgba);removed.append(pixels)
            if number>=start:
                ratio=(number-start)/(count-1-start)
                ratio=ratio*ratio*(3-2*ratio)
                rgba=morph(rgba,target,ratio,tracker,grid)
            canvas=Image.fromarray(rgba);display=canvas.resize((560,480),Image.Resampling.LANCZOS)
            new.append({'ms':record['ms'],'native':encode(packed,canvas),'display':encode(packed,display,True)})
            if number in (150,170,190,210,260,275,285,295):samples.append((number,before,rgba.copy()))
    temporary.replace(FOLDER/'pet-frames.bin')
    index['animations']['stomping']['frames']=new;index['data_bytes']=(FOLDER/'pet-frames.bin').stat().st_size
    (FOLDER/'pet-frames.json').write_text(json.dumps(index,separators=(',',':'))+'\n')
    metadata['version']=3
    metadata['handoff_repair']={'version':1,'reference':'assets/standing-obs.webp','reference_sha256':reference_sha,
        'floor_gap_cleanup':'remove only dark pixels outside the two boot fabric/outline envelopes',
        'removed_pixels_per_frame':removed,'morph_frames':[start,count-1],'morph_duration_seconds':HANDOFF_FRAMES/60,
        'endpoint':'pixel-exact standing frame 0; continue at standing frame 1',
        'runtime_outro_blending':False,'endpoint_camera_or_pose_cut':False}
    metadata['recovery']['handoff_source_seconds']=[metadata['source_range_seconds'][1]-HANDOFF_FRAMES/60,metadata['source_range_seconds'][1]]
    metadata['recovery']['handoff']='aligned costume/limb morph after the full video recovery; exact current idle endpoint'
    for name in ('pet-frames.bin','pet-frames.json'):
        p=FOLDER/name;metadata['files'][name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    (FOLDER/'source.json').write_text(json.dumps(metadata,indent=2)+'\n')
    sheet=Image.new('RGB',(8*220,2*260),'#e8e1e6');draw=ImageDraw.Draw(sheet)
    for col,(number,before,after) in enumerate(samples):
        for row,rgba in enumerate((before,after)):
            im=Image.fromarray(rgba)
            if number<260:im=im.crop((350,440,575,690))
            else:im=im.crop((295,75,590,690))
            im.thumbnail((215,235),Image.Resampling.LANCZOS);sheet.paste(im,(col*220,row*260+22),im)
        draw.text((col*220+5,4),str(number),fill='#332244')
    sheet.save(ROOT/'work/stomp-handoff-comparison.png')
    print(json.dumps({'frames':count,'floor_pixels_removed':sum(removed),'affected_gap_frames':sum(n>0 for n in removed),
                      'exact_endpoint':True,'handoff_frames':HANDOFF_FRAMES}),flush=True)


if __name__=='__main__':repair()
