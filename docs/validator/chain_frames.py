"""Chain per-frame SIFT similarity steps of a video into the first frame's pixel coordinates (S env, HD video path inside).

    python docs/validator/chain_frames.py START END STEP
"""
import cv2,numpy as np,os,json,sys
S=os.environ['S']
c=cv2.VideoCapture(r'C:/Users/Jordan/Desktop/Claude/p2-vod-seeds/data/challenge/wr_hd/wr27_hd.mp4')
A,B,STEP=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
sift=cv2.SIFT_create(3000)
def get(f):
    c.set(1,f);_,im=c.read();g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    m=np.full(g.shape,255,np.uint8); m[:120,:]=0; m[:,:230]=0; m[560:,:]=0; m[(g<25)]=0
    m=cv2.erode(m,np.ones((15,15),np.uint8))
    return g,m
H=np.eye(3); Hs={A:H.tolist()}
g0,m0=get(A); k0,d0=sift.detectAndCompute(g0,m0)
bf=cv2.BFMatcher()
for f in range(A+STEP,B+1,STEP):
    g1,m1=get(f); k1,d1=sift.detectAndCompute(g1,m1)
    ms=[m for m,n in bf.knnMatch(d1,d0,k=2) if m.distance<0.7*n.distance]
    p1=np.float32([k1[m.queryIdx].pt for m in ms]); p0=np.float32([k0[m.trainIdx].pt for m in ms])
    a_,inl=cv2.estimateAffinePartial2D(p1,p0,method=cv2.RANSAC,ransacReprojThreshold=3.0); h=np.vstack([a_,[0,0,1]])
    H=H@h; Hs[f]=H.tolist()
    print(f,len(ms),int(inl.sum()),np.round(h[:2,:3],3).tolist(),flush=True)
    k0,d0=k1,d1
json.dump(Hs,open(f'{S}/c27/H_{A}_{B}.json','w'))
