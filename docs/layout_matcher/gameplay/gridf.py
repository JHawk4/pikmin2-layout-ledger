"""gridf.py VIDEO FRAME OUT [N_AVG=1]: frame at 1280x720 with a 40px grid labelled in 1280-space."""
import cv2, sys, numpy as np
V = "C:/Users/Jordan/Desktop/Claude/p2-vod-seeds/.claude/worktrees/judge2-net-timesave-304bfd/data/challenge/wr/"
cap = cv2.VideoCapture(V + sys.argv[1]); f = int(sys.argv[2])
cap.set(cv2.CAP_PROP_POS_FRAMES, f); ok, im = cap.read()
im = cv2.resize(im, (1280, 720), interpolation=cv2.INTER_CUBIC)
for x in range(0, 1280, 80):
    cv2.line(im, (x, 0), (x, 720), (0, 200, 0), 1); cv2.putText(im, str(x), (x + 2, 12), 0, 0.4, (0, 255, 0), 1)
for y in range(0, 720, 80):
    cv2.line(im, (0, y), (1280, y), (0, 200, 0), 1); cv2.putText(im, str(y), (2, y + 12), 0, 0.4, (0, 255, 0), 1)
cv2.imwrite(sys.argv[3], im)
