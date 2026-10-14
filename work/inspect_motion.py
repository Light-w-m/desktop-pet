"""Review the largest native movement rather than treating it as a seam."""
from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageSequence,ImageDraw
root=Path(__file__).resolve().parent
stage=root/'repaired-assets'
manifest=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
for name in ['reading','drinking']:
    previous=None;peak=None
    with Image.open(stage/manifest['animations'][name]['file']) as im:
        for index,frame in enumerate(ImageSequence.Iterator(im)):
            rgba=frame.convert('RGBA');a=np.array(rgba)
            visible=a[:,:,:3].astype('float32')*a[:,:,3:4]/255
            if previous is not None:
                difference=float(np.abs(visible-previous[0]).mean())
                if peak is None or difference>peak[0]:peak=(difference,index,previous[1].copy(),rgba.copy())
            previous=(visible,rgba)
    width,height=manifest['canvas']
    sheet=Image.new('RGB',(width*2,height+20),'#30384c')
    for column,pose in enumerate(peak[2:]):sheet.paste(pose,(column*width,20),pose)
    ImageDraw.Draw(sheet).text((5,5),'%s frames %s -> %s'%(name,peak[1]-1,peak[1]),fill='white')
    sheet.save(root/(name+'-obs-motion.jpg'),quality=95)
    print(name,'largest movement at frame',peak[1],peak[0],flush=True)
