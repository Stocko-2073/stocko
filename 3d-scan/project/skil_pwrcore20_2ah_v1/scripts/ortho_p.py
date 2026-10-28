"""Rectify a capture of any placement onto a battery-frame plane (via the model registration).
Usage: ortho_p.py <req> <placement> <plane x|y|z> <h> <u0> <u1> <v0> <v1> [res] [--flipu]
 plane x: u=Y, v=Z at X=h ; plane y: u=X, v=Z at Y=h ; plane z: u=X, v=Y at Z=h"""
import sys
import cv2, numpy as np
from ac import OUT, Capture
from edgeprobe import placement_T, to_mat
args=[a for a in sys.argv[1:] if not a.startswith('--')]
req, pl, plane, h = args[0], args[1], args[2], float(args[3]); u0,u1,v0,v1 = map(float,args[4:8])
res = float(args[8]) if len(args)>8 else 0.1
cap=Capture(req); T=placement_T(pl)
us=np.arange(u0,u1,res); vs=np.arange(v1,v0,-res); U,V=np.meshgrid(us,vs)
if plane=='x': P=np.c_[np.full(U.size,h),U.ravel(),V.ravel()]
elif plane=='y': P=np.c_[U.ravel(),np.full(U.size,h),V.ravel()]
else: P=np.c_[U.ravel(),V.ravel(),np.full(U.size,h)]
uv=cap.project(to_mat(P,T)).astype(np.float32).reshape(U.shape+(2,))
img=cv2.remap(cap.image,uv[...,0],uv[...,1],cv2.INTER_CUBIC)
if '--flipu' in sys.argv: img=img[:,::-1].copy(); us=us[::-1]
for step,col,th in [(1,(110,110,110),1),(5,(0,160,255),1),(10,(0,0,255),1)]:
    for val in np.arange(np.ceil(min(u0,u1)/step)*step, max(u0,u1), step):
        x=int(np.argmin(abs(us-val)))
        if step==1 and val%5==0: continue
        if step==1: img[:,x]=(img[:,x]*0.7+np.array(col)*0.3).astype(np.uint8)
        else: cv2.line(img,(x,0),(x,img.shape[0]),col,th)
        if step==10: cv2.putText(img,f'{val:g}',(x+2,14),0,0.45,(0,0,255),1)
    for val in np.arange(np.ceil(v0/step)*step, v1, step):
        y=int(round((v1-val)/res))
        if not 0<=y<img.shape[0] or (step==1 and val%5==0): continue
        if step==1: img[y,:]=(img[y,:]*0.7+np.array(col)*0.3).astype(np.uint8)
        else: cv2.line(img,(0,y),(img.shape[1],y),col,th)
        if step==10: cv2.putText(img,f'{val:g}',(2,y-3),0,0.45,(0,0,255),1)
out=OUT/f'orthop_{req}_{plane}{h:g}.jpg'; cv2.imwrite(str(out),img); print(out,img.shape)
