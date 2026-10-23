"""Matte native walk and turn frames without mixing different RGB timestamps."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'work/sources/drag-deps'))
import cv2
import numpy as np
from PIL import Image

VIDEO=Path('E:/DJI_video/10月23日.mp4')
LOCAL=ROOT/'local-media/walking-video-20261023'
OLD=ROOT/'local-media/walking-video'
OUTPUT=ROOT/'assets/walking'
SIZE=(736,864)
RANGES={'left':(1.1,2.5),'right':(9.8,2.5),'pivot':(7.35,.35)}
cv2.setNumThreads(2)


def extract_source():
    LOCAL.mkdir(parents=True,exist_ok=True)
    for name,(start,duration) in RANGES.items():
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(start),'-i',str(VIDEO),'-t',str(duration),
            '-vf','fps=60,crop=1840:2160:840:0,scale=736:864:flags=lanczos',str(LOCAL/(name+'-%03d.png'))],check=True)
    for name,seconds in (('left',2),('right',11),('back',7.47)):
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(seconds),'-i',str(VIDEO),'-frames:v','1',
            '-vf','crop=1840:2160:840:0,scale=736:864',str(LOCAL/(name+'-reference.png'))],check=True)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def similarity(source,target,mask=None):
    sift=cv2.SIFT_create()
    a,da=sift.detectAndCompute(cv2.cvtColor(source,cv2.COLOR_RGB2GRAY),mask)
    b,db=sift.detectAndCompute(cv2.cvtColor(target,cv2.COLOR_RGB2GRAY),None)
    matches=[m for m,n in cv2.BFMatcher().knnMatch(da,db,k=2) if m.distance < .72*n.distance]
    transform,kept=cv2.estimateAffinePartial2D(np.float32([a[m.queryIdx].pt for m in matches]),
        np.float32([b[m.trainIdx].pt for m in matches]),method=cv2.RANSAC,ransacReprojThreshold=4)
    if transform is None or kept.sum()<20:raise ValueError('Unreliable alpha registration')
    return transform,int(kept.sum())


def guides():
    result={};registrations={}
    for name in ('left','left-cross','right','right-cross'):
        rgb=np.asarray(Image.open(OLD/f'{name}-guide-source.png').convert('RGB'))
        alpha=np.asarray(Image.open(OLD/f'{name}-registered-alpha.png').convert('L'))
        target=np.asarray(Image.open(LOCAL/('left-reference.png' if name.startswith('left') else 'right-reference.png')).convert('RGB'))
        transform,inliers=similarity(rgb,target,np.uint8(alpha>220)*255)
        rgb=cv2.warpAffine(rgb,transform,SIZE);alpha=cv2.warpAffine(alpha,transform,SIZE)
        result[name]=(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),alpha)
        registrations[name]={'transform':transform.tolist(),'inliers':inliers,'alpha_sha256':digest(OLD/f'{name}-registered-alpha.png')}
    rgb=np.asarray(Image.open(LOCAL/'back-reference.png').convert('RGB'))
    guide=np.asarray(Image.open(LOCAL/'back-guide.png').convert('RGBA'))
    transform,inliers=similarity(guide[:,:,:3],rgb,np.uint8(guide[:,:,3]>220)*255)
    result['back']=(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),cv2.warpAffine(guide[:,:,3],transform,SIZE))
    registrations['back']={'transform':transform.tolist(),'inliers':inliers,'alpha_sha256':digest(LOCAL/'back-guide.png')}
    for name,(_,alpha) in result.items():Image.fromarray(alpha).save(LOCAL/f'{name}-registered-alpha.png')
    return result,registrations


def matte(rgb,bank):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    r,g,b=rgb.astype('float32').transpose(2,0,1)
    pale=(r>g*.96)&(r>b*.69)&(r>90)
    guide=min(bank,key=lambda q:np.logical_xor(pale[480:840],q[1][480:840]>128).sum())
    flow=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(gray,guide[0],None)
    yy,xx=np.mgrid[:SIZE[1],:SIZE[0]].astype('float32')
    prior=cv2.remap(guide[1],xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_LINEAR)
    inside=np.uint8(prior>110);core=cv2.erode(inside,np.ones((7,7),'uint8'))>0
    outer=cv2.dilate(inside,np.ones((91,91),'uint8'))>0
    recovered=cv2.dilate(pale.astype('uint8'),np.ones((25,25),'uint8'))>0
    labels=np.zeros(gray.shape,'uint8');labels[outer|recovered]=cv2.GC_PR_BGD
    labels[inside>0]=cv2.GC_PR_FGD;labels[core]=cv2.GC_FGD
    labels[(r<b*.59)&(r<115)]=cv2.GC_BGD
    labels[pale]=cv2.GC_FGD;labels[(np.max(rgb,axis=2)<28)&~core]=cv2.GC_BGD
    # The distant NPC can touch the pet's hair in screen space. In the head
    # region use the registered/tracked silhouette instead of colour seeds.
    head_outline=cv2.dilate(np.uint8(prior>90),np.ones((5,5),'uint8'))>0
    labels[(yy<435)&~head_outline]=cv2.GC_BGD
    # The NPC's cream/green clothing is warmer than the blue-lit white/lilac
    # pet costume; exclude it even when optical flow follows it near hair.
    npc=(g>r*.88)&(g>b*1.08)&(r>b*1.05)&(r>65)&(yy<435)
    labels[npc]=cv2.GC_BGD
    labels[:130]=cv2.GC_BGD;labels[:,:185]=cv2.GC_BGD
    cv2.grabCut(rgb,labels,None,np.zeros((1,65),'float64'),np.zeros((1,65),'float64'),3,cv2.GC_INIT_WITH_MASK)
    mask=np.isin(labels,(1,3)).astype('uint8')
    count,components,stats,_=cv2.connectedComponentsWithStats(mask)
    primary=1+np.argmax(stats[1:,cv2.CC_STAT_AREA])
    near=cv2.dilate(np.uint8(components==primary),np.ones((17,17),'uint8'))>0
    keep=[primary]+[i for i in range(1,count) if stats[i,cv2.CC_STAT_TOP]>=435 and
        stats[i,cv2.CC_STAT_AREA]>=5 and np.any((components==i)&near&(prior>100))]
    selected=cv2.morphologyEx(np.uint8(np.isin(components,keep)),cv2.MORPH_CLOSE,np.ones((3,3),'uint8'))
    alpha=np.uint8(np.clip(cv2.GaussianBlur(selected.astype('float32'),(0,0),.45)*255+.5,0,255))
    return np.dstack((rgb,alpha))


def colour_curve(reference):
    target=np.asarray(Image.open(ROOT/'assets/standing-obs.webp').convert('RGBA'))
    a=cv2.erode(np.uint8(reference[:,:,3]>220),np.ones((5,5),'uint8'))>0
    b=cv2.erode(np.uint8(target[:,:,3]>220),np.ones((5,5),'uint8'))>0
    q=[2,10,25,50,75,90,98]
    src=np.percentile(reference[:,:,:3][a],q,axis=0);dst=np.percentile(target[:,:,:3][b],q,axis=0)
    curves=np.stack([np.interp(np.arange(256),np.r_[0,src[:,c],255],np.r_[0,dst[:,c],255]) for c in range(3)],axis=1)
    curves=np.uint8(np.clip(curves*.8+np.arange(256)[:,None]*.2+.5,0,255))
    return curves,{'source_rgb':src.tolist(),'target_rgb':dst.tolist(),'strength':.8,'fixed_for_all_clips':True}


def clean_head(rgba,direction):
    if direction!='right':return rgba
    rgba=rgba.copy();r,g,b=rgba[:,:,:3].astype('float32').transpose(2,0,1)
    yy,xx=np.mgrid[:SIZE[1],:SIZE[0]]
    pink=(r>g*1.12)&(b>g*1.1)&(r>100)&(yy>270)&(yy<365)&(rgba[:,:,3]>200)
    if pink.any():
        center=np.median(xx[pink])
        # Remaining grey NPC fragments sit behind the left edge of pink hair.
        # Keep the face, eye mask, shoulder whites and the actual pink strands.
        fragment=(xx<center-10)&(yy>270)&(yy<365)&(g>r*.95)&(r<b*.96)&(r>55)
        rgba[fragment,3]=0
    return rgba


def placement(rgba):
    yy,xx=np.where(rgba[:,:,3]>128);top,bottom=int(yy.min()),int(yy.max())
    scale=568/(bottom-top);waist=top+round((bottom-top)*.47)
    core=cv2.erode(np.uint8(rgba[:,:,3]>220),np.ones((11,11),'uint8'))
    center=float(np.median(np.where(core[waist-8:waist+9]>0)[1]))
    return np.array([[scale,0,445-center*scale],[0,scale,98-top*scale]],'float32')


def prepared(rgba,curve,transform):
    rgb=np.stack([curve[rgba[:,:,c],c] for c in range(3)],axis=2).astype('float32')
    rgb+=.3*np.clip(rgb-cv2.GaussianBlur(rgb,(0,0),.8),-8,8)
    value=np.concatenate((np.clip(rgb,0,255)*rgba[:,:,3:4]/255,rgba[:,:,3:4]),axis=2).astype('float32')
    value=cv2.warpAffine(value,transform,(840,720),flags=cv2.INTER_LANCZOS4)
    value[:,:,:3]=np.divide(value[:,:,:3]*255,value[:,:,3:4],out=np.zeros_like(value[:,:,:3]),where=value[:,:,3:4]>.01)
    return Image.fromarray(np.uint8(np.clip(value,0,255)))


def encode(stream,image,display=False):
    box=image.getbbox();tile=np.asarray(image.crop(box)).copy()
    if display:
        tile[:,:,:3]=tile[:,:,:3].astype('uint16')*tile[:,:,3:4]//255;tile=tile[:,:,[2,1,0,3]]
    payload=zlib.compress(tile.tobytes(),3);record=[stream.tell(),len(payload),*box];stream.write(payload);return record


def build(samples=False,reuse=False):
    OUTPUT.mkdir(exist_ok=True,parents=True)
    bank,registrations=guides();all_frames={};source_maps={};layouts={}
    for direction,(start,duration) in RANGES.items():
        paths=sorted(LOCAL.glob(direction+'-[0-9][0-9][0-9].png'));indices=list(range(len(paths)))
        if not paths:raise FileNotFoundError('Missing source frames; run with --extract')
        if samples:indices=[round(i*(len(paths)-1)/7) for i in range(8)]
        refs=[bank[direction],bank[direction+'-cross']] if direction!='pivot' else list(bank.values())
        def process(i):
            cached=LOCAL/f'{direction}-matte-{i:03}.png'
            if reuse and cached.is_file():rgba=np.asarray(Image.open(cached).convert('RGBA'))
            else:
                rgba=matte(np.asarray(Image.open(paths[i]).convert('RGB')),refs)
            rgba=clean_head(rgba,direction);Image.fromarray(rgba).save(cached)
            return i,rgba
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(process,indices))
        all_frames[direction]=[rgba for i,rgba in results];source_maps[direction]=[i for i,rgba in results]
        print(direction,len(results),'native source frames matted',flush=True)
    curve,colour=colour_curve(all_frames['left'][len(all_frames['left'])//2])
    for direction,frames in all_frames.items():
        layouts[direction]=placement(frames[len(frames)//2]);all_frames[direction]=[prepared(rgba,curve,layouts[direction]) for rgba in frames]
    if samples:
        for direction,frames in all_frames.items():
            sheet=Image.new('RGBA',(1120,960),'#d7cbd3')
            for i,im in enumerate(frames):
                im=im.resize((280,240),Image.Resampling.LANCZOS);sheet.alpha_composite(im,(i%4*280,i//4*480))
                dark=Image.new('RGBA',im.size,'#20242b');dark.alpha_composite(im);sheet.paste(dark,(i%4*280,i//4*480+240))
            sheet.convert('RGB').save(LOCAL/f'{direction}-samples.jpg')
        return
    details={};loops={}
    for direction in ('left','right'):
        frames=all_frames[direction];small=[]
        for im in frames:
            arr=np.asarray(im.resize((210,180))).astype('float32');arr[:,:,:3]*=arr[:,:,3:4]/255;small.append(arr)
        candidates=[]
        for a in range(len(frames)):
            for b in range(a+54,min(len(frames),a+88)):
                diff=np.abs(small[a]-small[b]).mean()
                velocity=np.abs((small[min(a+1,len(frames)-1)]-small[a])-(small[min(b+1,len(frames)-1)]-small[b])).mean()
                candidates.append((diff+.35*velocity,a,b))
        score,a,b=min(candidates);loops[direction]=frames[a:b]
        details[direction]={'source_range_seconds':[RANGES[direction][0]+a/60,RANGES[direction][0]+b/60],
            'source_frame_indices':[round(RANGES[direction][0]*120)+i*2 for i in source_maps[direction][a:b]],
            'loop_score':float(score),'output_frames':b-a,'duration_ms':round((b-a)*1000/60)}
    loops['turn']=all_frames['pivot'];details['turn']={'source_range_seconds':[7.35,7.7],
        'source_frame_indices':[882+i*2 for i in source_maps['pivot']],'output_frames':len(loops['turn']),
        'duration_ms':round(len(loops['turn'])*1000/60),'reverse_for_right_to_left':True}
    index={'version':1,'canvas':[840,720],'display_canvas':[560,480],'data':'pet-frames.bin','animations':{}};previews=[]
    with (OUTPUT/'pet-frames.bin').open('wb') as packed:
        for direction,frames in loops.items():
            records=[]
            for i,canvas in enumerate(frames):
                display=canvas.resize((560,480),Image.Resampling.LANCZOS)
                records.append({'ms':round((i+1)*1000/60)-round(i*1000/60),'native':encode(packed,canvas),'display':encode(packed,display,True)})
                if i in [round(j*(len(frames)-1)/3) for j in range(4)]:previews.append(display)
                if i==0:display.save(ROOT/f'work/walking-{direction}-cutout.png')
            index['animations']['walking_'+direction]={'frames':records}
        # Opposite turn reuses the same source pixels and byte offsets.
        index['animations']['walking_turn_back']={'frames':list(reversed(index['animations']['walking_turn']['frames']))}
    details['turn_back']=dict(details['turn'],source_frame_indices=list(reversed(details['turn']['source_frame_indices'])))
    index['data_bytes']=(OUTPUT/'pet-frames.bin').stat().st_size
    (OUTPUT/'pet-frames.json').write_text(json.dumps(index,separators=(',',':'))+'\n',encoding='utf-8')
    metadata={'version':2,'source_file':VIDEO.name,'source_sha256':digest(VIDEO),'source_fps':120,'output_fps':60,
        'crop':[840,0,1840,2160],'processing_size':list(SIZE),'directions':details,'one_original_frame_per_output':True,
        'rgb_temporal_blending':False,'synthetic_interpolation':False,'turn':'recorded turn, reversed for opposite direction',
        'colour_match':colour,'fixed_placement':{n:t.tolist() for n,t in layouts.items()},
        'alpha_references':{'tool':'image_gen__imagegen','mode':'built-in','use':'registered alpha only; no generated RGB',
            'reused_guide_folder':'local-media/walking-video','new_guide_folder':'local-media/walking-video-20261023',
            'prompt':(LOCAL/'mask-prompt.txt').read_text(encoding='utf-8'),'registrations':registrations},
        'files':{n:{'bytes':(OUTPUT/n).stat().st_size,'sha256':digest(OUTPUT/n)} for n in ('pet-frames.bin','pet-frames.json')}}
    (OUTPUT/'source.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sheet=Image.new('RGBA',(1120,720),'#dacfd7')
    for i,im in enumerate(previews):sheet.alpha_composite(im.resize((280,240)),(i%4*280,i//4*240))
    sheet.convert('RGB').save(ROOT/'work/walking-contact.jpg');print(json.dumps(details),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--samples',action='store_true')
    parser.add_argument('--extract',action='store_true');parser.add_argument('--reuse-mattes',action='store_true')
    args=parser.parse_args()
    if args.extract:extract_source()
    build(args.samples,args.reuse_mattes)
