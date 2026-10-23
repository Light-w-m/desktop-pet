"""Replace only the costume-tail regions from their original recorded frames."""
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw

from extract_obs import AFFINE, CANVAS, CROP, SOURCES, layout, mix
from standing_matte import RIBBON_REPAIR_REGIONS, crop_rect, ribbon_alpha

ROOT=Path(__file__).resolve().parent.parent
LOCAL=ROOT/'local-media/standing-ribbon-fix-20261023'
BACKUP=ROOT/'backups/before-gait-ribbon-fix-20261023/assets'


def native_boxes():
    boxes=[]
    for x,y,X,Y in RIBBON_REPAIR_REGIONS:
        points=np.float32([[[x-CROP[0],y-CROP[1]],[X-CROP[0],Y-CROP[1]]]])
        a,b=cv2.transform(points,AFFINE)[0]
        boxes.append((int(a[0])+1,int(a[1])+1,int(b[0])-1,int(b[1])-1))
    return boxes


def patch(rgb):
    rgba=np.zeros((CROP[3]-CROP[1],CROP[2]-CROP[0],4),'uint8')
    for rect in RIBBON_REPAIR_REGIONS:
        x,y,X,Y=rect;tile=crop_rect(rgb,rect)
        rgba[y-CROP[1]:Y-CROP[1],x-CROP[0]:X-CROP[0]]=np.dstack((tile,ribbon_alpha(tile)))
    rgba[rgba[:,:,3]==0,:3]=0
    return layout(rgba)


def main():
    LOCAL.mkdir(parents=True,exist_ok=True)
    boxes=native_boxes();manifest=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))
    cap=cv2.VideoCapture(str(SOURCES['standing'][0]))
    cap.set(cv2.CAP_PROP_POS_FRAMES,945)
    ok,bgr=cap.read();assert ok
    canonical=patch(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB));cap.release()
    report={'native_regions':[list(b) for b in boxes],'method':'per-frame fabric segmentation from original RGB; no temporal warping',
            'outside_regions_unchanged':True,'animations':{}}
    sheet=Image.new('RGB',(7*280,2*150),'#252b3b');draw=ImageDraw.Draw(sheet)
    for name,spec in manifest['animations'].items():
        path=ROOT/'assets'/spec['file'];count=spec['frames']
        # Always use a preserved input so reruns cannot compound the patch.
        original=BACKUP/spec['file']
        if not original.exists():
            import shutil
            shutil.copy2(path,original)
        output=LOCAL/spec['file']
        cap=cv2.VideoCapture(str(SOURCES[name][0]));position=None
        touched=0
        process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgba',
            '-s','840x720','-framerate','60','-i','pipe:0','-an','-c:v','libwebp_anim','-lossless','1',
            '-compression_level','0','-loop','0',str(output)],stdin=subprocess.PIPE)
        with Image.open(original) as source:
            assert source.n_frames==count
            for i in range(count):
                source.seek(i);pose=source.convert('RGBA')
                if name=='standing' or i<12 or i>=count-12:
                    wanted=round(SOURCES[name][1]*60)+i
                    if wanted!=position:cap.set(cv2.CAP_PROP_POS_FRAMES,wanted)
                    ok,bgr=cap.read();assert ok
                    position=wanted+1
                    fixed=patch(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
                    if i<12:fixed=mix(canonical,fixed,i/11)
                    if i>=count-12:fixed=mix(fixed,canonical,(i-(count-12))/11)
                    before=pose.copy()
                    for box in boxes:pose.paste(fixed.crop(box),box[:2])
                    # Verify the pixel diff is confined to the costume tails.
                    a,b=np.array(before),np.array(pose)
                    for x,y,X,Y in boxes:a[y:Y,x:X]=b[y:Y,x:X]
                    assert np.array_equal(a,b)
                    touched+=1
                    if name=='standing' and i in (0,24,60,80,98,120,152):
                        col=(0,24,60,80,98,120,152).index(i)
                        for row,im in enumerate((before,pose)):
                            tile=im.crop((325,435,590,510)).resize((280,80))
                            sheet.paste(tile,(col*280,row*150+25),tile)
                        draw.text((col*280+8,5),str(i),fill='white')
                process.stdin.write(pose.tobytes())
        process.stdin.close();assert process.wait()==0
        cap.release()
        with Image.open(output) as encoded:
            assert encoded.n_frames==count
            duration=0
            for i in range(count):encoded.seek(i);encoded.load();duration+=encoded.info['duration']
            assert duration==spec['duration_ms']
        output.replace(path)
        report['animations'][name]={'repaired_frames':touched,'total_frames':count,'duration_ms':duration}
        print(name,touched,'ribbon frames repaired',flush=True)
    manifest['standing_matting']['ribbons']='current-frame costume fabric segmentation; no tracked background pixels'
    (ROOT/'assets/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checksums=json.loads((ROOT/'assets/source-checksums.json').read_text())
    for spec in manifest['animations'].values():
        p=ROOT/'assets'/spec['file']
        checksums['files'][p.name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    (ROOT/'assets/source-checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
    sheet.save(ROOT/'work/standing-ribbon-comparison.png')
    (LOCAL/'repair.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
