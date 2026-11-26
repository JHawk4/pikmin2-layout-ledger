import cv2, sys, os
V = "C:/Users/Jordan/Desktop/Claude/p2-vod-seeds/.claude/worktrees/judge2-net-timesave-304bfd/data/challenge/wr/"
name, out = sys.argv[1], sys.argv[2]
cap = cv2.VideoCapture(V + name)
print(name, cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT), cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT))
for f in sys.argv[3:]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(f)); ok, im = cap.read()
    cv2.imwrite(os.path.join(out, f"{os.path.splitext(name)[0]}_{f}.jpg"), im)
