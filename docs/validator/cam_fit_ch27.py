"""CH27-1 camera fit: a pinhole camera for HD frame 575 fitted to typed marks (pod, Gyroid Bust,
marbles, falling-rock shadow centres chained in from later frames), per candidate seed.
Lower mean residual = better. Marks: obs/ch27_1_f575.json. Used for the CH27-1 17864AAB verdict.
"""
import sys,os,json,numpy as np
from scipy.optimize import least_squares
sys.path.insert(0,'docs/layout_matcher'); import lm
MARKS=[((835,545),'pod',0),((620,470),'haniwa',1),((505,-80),'be_dama_blue_l',2),((386,-169),'be_dama_red_l',2),
       ((425,133),'rock',0),((347,4),'rock',0),((327,34),'rock',0),((237,-135),'rock',0)]
def proj(p,pts):
    ta,ts,psi,th,D,f,hs,hm=p
    a,s,hk=pts[:,0],pts[:,1],pts[:,2]
    z=np.where(hk==1,hs,np.where(hk==2,hm,0.0))
    c,si=np.cos(psi),np.sin(psi)
    # rotate floor into view frame: forward (along view), right
    da,ds=a-ta,s-ts
    fw=da*c+ds*si; rt=-da*si+ds*c
    # camera at distance D behind target, pitched down th
    ct,st=np.cos(th),np.sin(th)
    zc=fw*ct+D-z*st*(-1)*(-1)  # depth
    zc=D+fw*ct-z*st
    yc=fw*st+z*ct              # up in image
    return np.stack([640+f*rt/zc,360-f*yc/zc],1)
def fit(objs,init=None):
    # objs: dict name->list of (ahead,side)
    best=None
    p0=np.array(init if init is not None else [400,-200,0,0.8,1500,1500,60,80],float)
    assign=None
    for it in range(4):
        pts=[];scr=[]
        for (xy,n,hk) in MARKS:
            cands=objs.get(n,[])
            if not cands: continue
            if assign is None or n!='rock':
                q=cands[0] if n!='rock' else None
            if n=='rock':
                if assign is None: continue
                P=proj(p0,np.array([[a,s,0] for a,s in cands],float))
                q=cands[int(np.argmin(np.hypot(*(P-np.array(xy)).T)))]
            pts.append([q[0],q[1],hk]); scr.append(xy)
        pts=np.array(pts,float); scr=np.array(scr,float)
        r=least_squares(lambda p:(proj(p,pts)-scr).ravel(),p0,loss='soft_l1',f_scale=20,
            bounds=([-3000,-3000,-np.pi*2,0.2,300,300,0,0],[3000,3000,np.pi*2,1.5,6000,6000,150,250]))
        p0=r.x; assign=True
    res=np.hypot(*(proj(p0,pts)-scr).T)
    res=np.concatenate([res,[999]*(len(MARKS)-len(res))])
    return p0,res
def objs_of(l):
    d={'pod':[(0.0,0.0)]}
    for o in l['objects']: d.setdefault(o['names'][0],[]).append((o['ahead'],o['side']))
    return d
if __name__=='__main__':
    for s in [0x17864AAB,0x10721F7F]:
        l=lm.dump('CH27-1',s)[0]; best=None
        for psi in np.linspace(-np.pi,np.pi,12,endpoint=False):
            r=fit(objs_of(l),[400,-200,psi,0.8,1500,1500,60,80])
            if r and (best is None or np.median(r[1])+r[1].mean()<np.median(best[1])+best[1].mean()): best=r
        print(f'{s:08X}',np.round(best[1]).tolist(),np.round(best[0],2).tolist())
