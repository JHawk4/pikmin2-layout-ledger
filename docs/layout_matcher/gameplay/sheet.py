"""Contact sheet: sheet.py VIDEO OUT.jpg START STEP [N=16] [COLS=4] [W=400]"""
import cv2, sys, numpy as np
V = "C:/Users/Jordan/Desktop/Claude/p2-vod-seeds/.claude/worktrees/judge2-net-timesave-304bfd/data/challenge/wr/"
name, out, start, step = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
n = int(sys.argv[5]) if len(sys.argv) > 5 else 16
cols = int(sys.argv[6]) if len(sys.argv) > 6 else 4
w = int(sys.argv[7]) if len(sys.argv) > 7 else 400
cap = cv2.VideoCapture(V + name if "/" not in name else name)
tiles = []
for i in range(n):
    f = start + i * step
    cap.set(cv2.CAP_PROP_POS_FRAMES, f); ok, im = cap.read()
    if not ok: im = np.zeros((360, 640, 3), np.uint8)
    im = cv2.resize(im, (w, int(w * im.shape[0] / im.shape[1])))
    cv2.putText(im, str(f), (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    tiles.append(im)
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
