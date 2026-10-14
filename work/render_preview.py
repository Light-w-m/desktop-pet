from pathlib import Path
import bisect
import json
import subprocess
from PIL import Image,ImageDraw,ImageFont,ImageSequence

ROOT=Path(__file__).resolve().parent
old=ROOT.parent/'backups'/'before-full-idles'/'assets'
new=ROOT/'repaired-assets'
font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',26)
small=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',22)
data={}
for version,folder in [('old',old),('new',new)]:
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name,spec in manifest['animations'].items():
        frames=[];ends=[];total=0
        with Image.open(folder/spec['file']) as im:
            for frame in ImageSequence.Iterator(im):
                frames.append(frame.convert('RGBA'));total+=im.info['duration'];ends.append(total)
        data[version,name]=(frames,ends,total)
output=ROOT.parent/'动作修复预览.mp4'
cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','rawvideo','-pixel_format','rgb24','-video_size','1200x980','-framerate','60','-i','pipe:0','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
process=subprocess.Popen(cmd,stdin=subprocess.PIPE)
try:
    for tick in range(1140):
        canvas=Image.new('RGB',(1200,980),(32,35,46));draw=ImageDraw.Draw(canvas)
        for col,(name,title) in enumerate([('standing','站立待机'),('drinking','坐着喝饮料'),('reading','趴着读书')]):
            x=col*400
            draw.text((x+125,8),title,font=font,fill=(238,238,247))
            for version,y,label in [('old',55,'原版'),('new',510,'修复后 · 60 FPS')]:
                draw.text((x+18,y),label,font=small,fill=(174,179,210) if version=='old' else (185,218,202))
                frames,ends,total=data[version,name]
                index=min(bisect.bisect_right(ends,(tick*1000/60)%total),len(frames)-1)
                canvas.paste(frames[index],(x,y+28),frames[index])
        process.stdin.write(canvas.tobytes())
finally:
    process.stdin.close()
if process.wait():raise RuntimeError('Preview encoding failed')
print(output)
