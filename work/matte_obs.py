from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

cv2.setNumThreads(2)
ROOT = Path(__file__).resolve().parent
CROP = (650, 150, 1950, 1335)

def matte(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    blue_pixels = (hsv[:,:,0] >= 100) & (hsv[:,:,0] <= 126) & (hsv[:,:,1] > 110)
    # The backdrop is cyan; the cushion's saturated royal blue is foreground.
    background = (hsv[:,:,0] >= 77) & (hsv[:,:,0] <= 108) & (hsv[:,:,1] > 35)
    seed = (~background).astype('uint8')
    # All floor reflections start below the character's lowest shoe.
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edge = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    # The sharp lower outline moves as the cushion bobs. Its blurred floor
    # reflection must never be added to the character's connected component.
    score = edge[1000:1172, 500:750].mean(axis=1)
    sharp = np.flatnonzero(score > 55)
    floor = int(sharp[-1]+1000+2) if len(sharp) else 1115
    seed[floor:] = 0
    n, labels, stats, centers = cv2.connectedComponentsWithStats(seed, 8)
    main = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    mask = (labels == main).astype('uint8')
    x, y, w, h, area = stats[main]
    for i in range(1, n):
        sx, sy, sw, sh, sa = stats[i]
        cx, cy = centers[i]
        if i != main and 150 < sa < 300000 and sx > 8 and sy > 8 and sx+sw < rgb.shape[1]-8 and sy+sh < floor and sw < 820 and sh < 1000 and x-450 < cx < x+w+350 and y-500 < cy < floor-8:
            part = labels[sy:sy+sh,sx:sx+sw] == i
            # Detached familiar/tassel details are violet/blue, unlike stars.
            local=hsv[sy:sy+sh,sx:sx+sw]
            familiar=np.mean(((local[:,:,0] >= 112) & (local[:,:,1] > 110))[part]) > .28 and cy<y+h+60
            # The cushion shrinks and separates during the recorded return.
            # Its white body with a cyan-blue rim is still part of the action.
            white=(local[:,:,1]<45)&(local[:,:,2]>120)
            # Test the blue rim in the bounding box, since the cyan key can
            # separate it from the white component before outline recovery.
            rim=np.mean(blue_pixels[sy:sy+sh,sx:sx+sw])>.03
            cushion=sa>400 and cy>y+h*.45 and np.mean(white[part])>.6 and (rim or sa>3000)
            warm=((local[:,:,0]>128)|(local[:,:,0]<35))&(local[:,:,1]>30)
            person=sa>6000 and np.mean(warm[part])>.15
            if familiar or cushion or person:
                mask[sy:sy+sh,sx:sx+sw][part] = 1
    # Restore enclosed details regardless of their cyan color.
    inverse = 1-mask
    nn, ll, ss, _ = cv2.connectedComponentsWithStats(inverse, 8)
    for i in range(1, nn):
        sx, sy, sw, sh, sa = ss[i]
        if sx > 0 and sy > 0 and sx+sw < rgb.shape[1] and sy+sh < rgb.shape[0] and sa < 80000:
            part = ll[sy:sy+sh,sx:sx+sw] == i
            if sa < 100 or np.mean(blue_pixels[sy:sy+sh,sx:sx+sw][part]) > .25:
                mask[sy:sy+sh,sx:sx+sw][part] = 1
    # Keep the native foreground topology. A global learned color model can
    # classify the cushion's lit blue underside as sky during its rotation.
    refined = mask.copy()
    # Toon outlines enclose blue fabric even when its color resembles the
    # backdrop. Recover those bounded regions using actual image edges.
    lines = cv2.Canny(gray, 30, 75)
    lines = cv2.morphologyEx(lines, cv2.MORPH_CLOSE, np.ones((3,3),'uint8'))
    contours, _ = cv2.findContours(lines, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        sx,sy,sw,sh = cv2.boundingRect(contour)
        if sw*sh > 400000 or sw*sh < 100:
            continue
        region = np.zeros((sh,sw),'uint8')
        cv2.drawContours(region,[contour-np.array([[[sx,sy]]])],-1,1,cv2.FILLED)
        selection = region.astype(bool)
        local_hsv = hsv[sy:sy+sh,sx:sx+sw]
        blue = (local_hsv[:,:,0] >= 104) & (local_hsv[:,:,0] <= 126) & (local_hsv[:,:,1] > 75)
        if np.mean(blue[selection]) > .35 and np.mean(refined[sy:sy+sh,sx:sx+sw][selection]) > .25:
            refined[sy:sy+sh,sx:sx+sw][selection] = 1
    nn,ll,ss,_ = cv2.connectedComponentsWithStats(1-refined,8)
    for i in range(1,nn):
        sx,sy,sw,sh,sa=ss[i]
        if sx>0 and sy>0 and sx+sw<rgb.shape[1] and sy+sh<rgb.shape[0] and sa<80000:
            part=ll[sy:sy+sh,sx:sx+sw]==i
            if sa<100 or np.mean(blue_pixels[sy:sy+sh,sx:sx+sw][part])>.25:
                refined[sy:sy+sh,sx:sx+sw][part]=1
    refined[floor:] = 0
    closed=cv2.morphologyEx(refined,cv2.MORPH_CLOSE,np.ones((51,51),'uint8'))
    refined[(closed==1)&blue_pixels]=1
    refined[floor:]=0
    alpha = cv2.GaussianBlur(refined.astype('float32'), (3,3), .55)
    alpha = np.clip(alpha*255, 0, 255).astype('uint8')
    alpha[alpha < 5] = 0
    out = np.dstack((rgb, alpha))
    out[alpha == 0, :3] = 0
    return out

if __name__ == '__main__':
    sheet = Image.new('RGB', (1500, 1440), '#171b29')
    draw = ImageDraw.Draw(sheet)
    for i, (number, second) in enumerate([(1,1.5),(1,3),(1,6),(1,8),(1,12),(1,14),(2,1),(2,3),(2,6),(2,10),(2,13),(2,15)]):
        path = Path(r'E:\OBS\video') / ('2026-10-14 21-04-%s.mp4' % ('10' if number == 1 else '51'))
        cap = cv2.VideoCapture(str(path))
        cap.set(cv2.CAP_PROP_POS_MSEC, second*1000)
        ok, bgr = cap.read()
        cap.release()
        x1,y1,x2,y2=CROP
        rgb = cv2.cvtColor(bgr[y1:y2,x1:x2],cv2.COLOR_BGR2RGB)
        rgba=Image.fromarray(matte(rgb))
        rgba.save(ROOT / ('obs-matte-%02d.png' % i))
        rgba.thumbnail((490,460),Image.Resampling.LANCZOS)
        x,y=i%3*500,i//3*360
        # Scale for overview, native PNGs remain available for edge inspection.
        rgba.thumbnail((470,330),Image.Resampling.LANCZOS)
        sheet.paste(rgba,(x+(500-rgba.width)//2,y+20),rgba)
        draw.text((x+10,y+6),'clip %s / %.1fs' % (number,second),fill='white')
    sheet.save(ROOT/'obs-matte-contact.jpg',quality=95)
