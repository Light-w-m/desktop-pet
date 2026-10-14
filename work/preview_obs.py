"""Render complete native poses on dark/light backdrops without raw caches."""
from pathlib import Path
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageSequence

ROOT=Path(__file__).resolve().parent
STAGE=ROOT/'repaired-assets'
manifest=json.loads((STAGE/'manifest.json').read_text(encoding='utf-8'))
font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',24)
video=ROOT.parent/'OBS动作预览.mp4'
process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1680x780','-framerate','60','-i','pipe:0','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
poster=Image.new('RGB',(1680,670),'#252b3b')
for name,title,column,sample in [('standing','站立待机',0,.7),('drinking','坐着喝饮料',1,8.0),('reading','趴着读书',2,7.0)]:
    count=manifest['animations'][name]['frames']
    qa_points={0:0,count//4:1,count//2:2,3*count//4:3,count-1:4}
    qa_sheet=Image.new('RGB',(560*5,480),'#1e212c')
    with Image.open(STAGE/manifest['animations'][name]['file']) as animation:
        elapsed=0
        captured=False
        for index,frame in enumerate(ImageSequence.Iterator(animation)):
            pose=frame.convert('RGBA')
            if index in qa_points:
                thumb=pose.resize((560,480),Image.Resampling.LANCZOS)
                qa_sheet.paste(thumb,(qa_points[index]*560,0),thumb)
            duration=animation.info['duration']
            if not captured and elapsed>=sample*1000:
                thumb=pose.resize((560,480),Image.Resampling.LANCZOS)
                poster.paste(thumb,(column*560,150),thumb)
                ImageDraw.Draw(poster).text((column*560+30,25),title,font=font,fill='white')
                captured=True
            elapsed+=duration
            image=Image.new('RGB',(1680,780),'#f2f1ed')
            ImageDraw.Draw(image).rectangle((0,0,839,779),fill='#252b3b')
            image.paste(pose,(0,55),pose)
            image.paste(pose,(840,55),pose)
            draw=ImageDraw.Draw(image)
            draw.text((24,14),title+' · 原生 60 FPS',font=font,fill='white')
            draw.text((864,14),'浅色背景边缘检查',font=font,fill='#252b3b')
            process.stdin.write(image.tobytes())
    qa_sheet.save(ROOT/(name+'-obs-qa.jpg'),quality=96)
process.stdin.close()
if process.wait():raise RuntimeError('Preview encoder failed')
poster.save(ROOT.parent/'references'/'obs-full-preview.png')
print(video)
