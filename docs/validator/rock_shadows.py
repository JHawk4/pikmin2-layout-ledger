"""Find falling-rock shadows (flat grey disks) in frames and map their centres through chain_frames.py output."""
import cv2,numpy as np,json,os
S=os.environ['S']
H=json.load(open(f'{S}/c27/H_575_820.json'))
c=cv2.VideoCapture(r'C:/Users/Jordan/Desktop/Claude/p2-vod-seeds/data/challenge/wr_hd/wr27_hd.mp4')
pts=[]
for f in range(641,821,2):
    if str(f) not in H: continue
    c.set(1,f);_,im=c.read(); im=cv2.GaussianBlur(im,(5,5),0).astype(int)
    b,g,r=im[...,0],im[...,1],im[...,2]
    m=((abs(b-g)<10)&(abs(g-r)<10)&(g>75)&(g<130)).astype(np.uint8)
    m[:120]=0; m[:,:230]=0; m[600:]=0
    m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((7,7),np.uint8))
    n,lab,st,cen=cv2.connectedComponentsWithStats(m)
    for i in range(1,n):
        x,y,w,h,a=st[i]
        if a<500 or a>12000: continue
        if not 0.7<w/h<1.4: continue
        fill=a/(w*h)
        if fill<0.65: continue
        p=np.array(H[str(f)])@[cen[i][0],cen[i][1],1]
        pts.append((f,int(cen[i][0]),int(cen[i][1]),int(p[0]),int(p[1]),int(w)))
for q in pts: print(*q)
json.dump(pts,open(f'{S}/c27/shadows.json','w'))
