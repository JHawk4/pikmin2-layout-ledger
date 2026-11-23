"""CH12: per-candidate pixel residual of the marked plants and Key on comedown frame 316, refitting
the camera per seed. Reads data/lm/ch12/ps2.npz (pointscan output); prints the best candidates."""
import sys,cv2,numpy as np
sys.path.insert(0,'docs/layout_matcher'); import comedown as cd, lm
TK={'ooinu_l','tukushi','wakame_l','tanpopo','clover','magaret','hikarikinoko'}; PL=TK|{'ooinu_s','kareooinu_s'}
M=[(455,297,{'clover'}),(622,540,TK),(755,350,PL),(892,467,PL),(972,440,PL),(1112,495,PL),(62,407,PL),(92,540,PL),(50,600,PL),(210,185,PL),(708,500,{'key'})]
z=np.load('data/lm/ch12/ps2.npz'); b=z['best']; ks=np.where(b>=8)[0]; st=lm.seed_at(0x0072844E,0)
S=[lm.seed_at(st,int(k))&0xFFFFFFFF for k in ks]; D=lm.dump('CH12-1',*S)
Hs=[(zz,t,cd.homography(1280,720,16/9,float(zz),float(t))) for zz in np.arange(1.3,1.51,0.025) for t in range(-6,5)]
SH=np.array([(dx,dy) for dx in range(-90,-9,10) for dy in range(0,71,10)],np.float32)
out=[]
for k,s,d in zip(ks,S,D):
  objs=[o for o in d['objects'] if o['names'][0] in PL|{'key'}]
  W=np.float32([[[o['side'],o['ahead']] for o in objs]]); best=(1e9,)
  for zz,t,H in Hs:
    q=cv2.perspectiveTransform(W,H)[0]
    tot=np.zeros(len(SH))
    for u,v,nm in M:
      idx=[i for i,o in enumerate(objs) if o['names'][0] in nm]
      if not idx: tot+=80; continue
      dd=np.linalg.norm(q[idx][None]+SH[:,None]-[u,v],axis=2).min(1); tot+=np.minimum(dd,80)
    j=int(tot.argmin())
    if tot[j]<best[0]: best=(round(float(tot[j])),round(float(zz),3),t,*SH[j])
  out.append((best,'%08X'%(s&0x7FFFFFFF),int(k)))
out.sort()
for o in out[:12]: print(o)
