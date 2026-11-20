import math, numpy as np
from p2seeds import rng
def f32(x): return float(np.float32(x))
def randf(s): return ((s>>16)&0x7fff)/32768.0
def dive_params(first_state):
    """first_state: RNG state whose value is the dive's first draw. Returns [colour][i] dicts."""
    s=first_state; out=[]
    for c in range(5):
        col=[]
        for i in range(50):
            r0=randf(s); s=rng.next_seed(s,1)
            r1=randf(s); s=rng.next_seed(s,1)
            r2=randf(s); s=rng.next_seed(s,1)
            r3=randf(s); s=rng.next_seed(s,1)
            dx=30*r1*(-1 if r2>0.5 else 1); dy=10*r3+15
            col.append(dict(T0=0.1*r0-(0.1*i+0.5*c), dx=dx, dy=dy, r=(r0,r1,r2,r3)))
        out.append(col)
    return out
def simulate(p, X0, Y0, goalX, goalY, i, nframes=80, circleY=100.0, speed=12.0, ts=0.15):
    """positions per update frame (frame 0 = first update after jumpStart)"""
    t=p['T0']; state=0; x,y=X0,Y0; ix,iy=X0,Y0; pos=[]
    for n in range(nframes):
        t+=ts
        if t>2*math.pi: t-=2*math.pi
        if state==0:
            if t>=0:
                if t>math.pi/2: state=3
                x=-(p['dx']*math.sin(t)-ix); y=iy-abs(math.sin(2*t)*p['dy'])
        elif state==3:
            if y>circleY: y-=speed
            else: state=4; ix,iy=x,y; t=0.0
        elif state==4:
            if t>math.pi: state=5; t=math.pi
            calc={0:-8.0,1:8.0}.get(i%3,0.0)
            x=ix+t*(goalX-ix+calc)/math.pi; y=-(math.sin(t)*70-iy)
        elif state==5:
            if y<goalY-40: y+=speed
            else: y=-100; state=6
        pos.append((x,y,state))
    return pos
