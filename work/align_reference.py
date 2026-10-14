from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parent

def align(source_path, donor_path, output_path, height):
    source=np.array(Image.open(source_path).convert('RGB'))
    donor=np.array(Image.open(donor_path).convert('RGBA'))
    gray1=cv2.cvtColor(donor[:,:,:3],cv2.COLOR_RGB2GRAY)
    gray2=cv2.cvtColor(source,cv2.COLOR_RGB2GRAY)
    sift=cv2.SIFT_create(nfeatures=8000)
    k1,d1=sift.detectAndCompute(gray1,(donor[:,:,3]>180).astype('uint8')*255)
    k2,d2=sift.detectAndCompute(gray2,None)
    pairs=cv2.BFMatcher().knnMatch(d1,d2,k=2)
    matches=[a for a,b in pairs if a.distance<.73*b.distance]
    a=np.float32([k1[m.queryIdx].pt for m in matches])
    b=np.float32([k2[m.trainIdx].pt for m in matches])
    matrix,keep=cv2.estimateAffinePartial2D(a,b,method=cv2.RANSAC,ransacReprojThreshold=2.0,maxIters=10000)
    if matrix is None or int(keep.sum())<12:
        raise ValueError(f'Insufficient registration matches: {len(matches)}')
    errors=np.linalg.norm(a@matrix[:,:2].T+matrix[:,2]-b,axis=1)
    print(output_path.name,'matches',len(matches),'inliers',int(keep.sum()),'error',float(np.median(errors[keep[:,0]>0])), 'matrix',matrix.tolist(),flush=True)
    warp=cv2.warpAffine(donor,matrix,(source.shape[1],height),flags=cv2.INTER_LANCZOS4)
    Image.fromarray(warp).save(output_path)
    qa=np.full((height,source.shape[1],3),40,np.uint8)
    qa[:source.shape[0]]=source
    edges=cv2.Canny(warp[:,:,3],100,200)
    qa[edges>0]=(255,50,50)
    Image.fromarray(qa).save(output_path.with_name(output_path.stem+'-alignment.png'))
    return matrix

if __name__=='__main__':
    align(ROOT/'reading-source-first.png',Path(r'C:\Users\Lightw\.codex\generated_images\01a13a18-d38a-7242-bcc3-11044715e178\exec-f7a198aa-b8ba-4ea6-9e32-3488f95c2671.png'),ROOT/'reading-complete-reference.png',400)
