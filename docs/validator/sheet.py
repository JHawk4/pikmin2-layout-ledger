"""Contact sheet of video frames, each labelled with its frame number.

    python docs/validator/sheet.py VIDEO START END STEP OUT.jpg [--cols 4] [--w 480] [--crop x0,y0,x1,y1]
    python docs/validator/sheet.py VIDEO FRAME FRAME 1 OUT.png --w 1280     (one full frame)
"""
import sys

import cv2
import numpy as np


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    video, a, b, step, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    cols, w = int(arg("--cols", 4)), int(arg("--w", 480))
    crop = arg("--crop", None)
    cap = cv2.VideoCapture(video)
    tiles = []
    for f in range(a, b + 1, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, img = cap.read()
        if not ok:
            break
        if crop:
            x0, y0, x1, y1 = map(int, crop.split(","))
            img = img[y0:y1, x0:x1]
        h = int(img.shape[0] * w / img.shape[1])
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        cv2.putText(img, str(f), (6, 22), 0, 0.7, (0, 0, 0), 4)
        cv2.putText(img, str(f), (6, 22), 0, 0.7, (0, 255, 255), 2)
        tiles.append(img)
    if not tiles:
        sys.exit("no frames")
    h = tiles[0].shape[0]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(out, np.vstack(rows))
    print(out, len(rows), "rows", "fps", cap.get(cv2.CAP_PROP_FPS), "n", int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))


if __name__ == "__main__":
    main()
