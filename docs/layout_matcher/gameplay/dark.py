"""dark.py VIDEO [STEP=6]: print frame ranges where the frame is near-black (floor transitions)."""
import cv2, sys
V = "C:/Users/Jordan/Desktop/Claude/p2-vod-seeds/.claude/worktrees/judge2-net-timesave-304bfd/data/challenge/wr/"
cap = cv2.VideoCapture(V + sys.argv[1]); step = int(sys.argv[2]) if len(sys.argv) > 2 else 6
f = 0; run = None
while True:
    ok, im = cap.read()
    if not ok: break
    if f % step == 0:
        m = im.mean()
        if m < 8:
            run = run or [f, f]; run[1] = f
        elif run:
            print("dark", run); run = None
    f += 1
