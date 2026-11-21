"""Extract the challenge-select dive sprites from a Pikmin 2 (GameCube) disc image.

    python docs/challenge_dive/extract_sprites.py "Pikmin 2.iso" [--out data/game/dive_sprites.npz]

Each dive Pikmin is drawn by TChallengePiki::draw (pikmin2-decomp, plugProjectMorimuraU/
challengeSelect2D.cpp) from three panes of challengemodo_select.blo (in new_screen/eng/
res_challengeSelect.szs), per colour X in r, y, b, w, bl:
  pane0 = PX_pk_l (white: Pw_pk_r)  an anchor: pikmin_body_a.bti with material alpha 0
  pane1 = PX_pk_r (white: PICT_020) the body, new_X_pikmin.bti, drawn with negative width (mirrored)
  pane2 = PX_fw                     the flower, flower_icon.bti (white/purple: tinted magenta->white)
at, for a Pikmin at position p (game screen units, 640x480, y down):
  pane0 rect: p + [0, w0] x [0, h0]
  pane1 rect: p - vec0 + [-w1, 0] x [0, h1]     (vec0 = pane0 bottom-left - pane1 bottom-right)
  pane2 rect: p - vec1 + [0, w2] x [0, h2]      (vec1 = pane0 bottom-left - pane2 bottom-left)
The Pikmin start at p = pane0's BtmLeft vertex, which is its top-left on screen (J2D's
"bottom" is the smaller y), so at the start the three panes sit exactly on the menu icon. Draw order: colours red, yellow, blue, white, purple;
within a colour index 49 first, 0 last (on top).

The textures are the game's own art, so the output goes to data/ (not committed).
Writes an npz with, per colour: body/flower RGBA float32 images (as drawn: body already mirrored),
their rects relative to p (x0, y0, x1, y1 in game units), and the start position.
"""

import argparse
import os
import struct
import sys

import numpy as np

COLS = [("red", "r"), ("yellow", "y"), ("blue", "b"), ("white", "w"), ("purple", "bl")]


def yaz0(data):
    if data[:4] != b"Yaz0":
        return data
    size = struct.unpack(">I", data[4:8])[0]
    out = bytearray(size)
    s, d = 16, 0
    while d < size:
        code = data[s]
        s += 1
        for bit in range(8):
            if d >= size:
                break
            if code & (0x80 >> bit):
                out[d] = data[s]
                d += 1
                s += 1
            else:
                b1, b2 = data[s], data[s + 1]
                s += 2
                dist = ((b1 & 0xF) << 8 | b2) + 1
                n = b1 >> 4
                if n == 0:
                    n = data[s] + 0x12
                    s += 1
                else:
                    n += 2
                for _ in range(n):
                    out[d] = out[d - dist]
                    d += 1
    return bytes(out)


def rarc(data):
    """{name: bytes} of a RARC archive (flat; names only)."""
    u32 = lambda o: struct.unpack(">I", data[o:o + 4])[0]  # noqa: E731
    u16 = lambda o: struct.unpack(">H", data[o:o + 2])[0]  # noqa: E731
    info = 0x20
    n_files, file_off, str_off = u32(info + 0x08), u32(info + 0x0C) + 0x20, u32(info + 0x14) + 0x20
    data_off = u32(0x0C) + 0x20
    out = {}
    for i in range(n_files):
        e = file_off + 0x14 * i
        attr = data[e + 4]
        if attr & 0x02:          # directory
            continue
        name_o = u16(e + 6)
        name = data[str_off + name_o:data.index(b"\0", str_off + name_o)].decode("latin1")
        out[name] = data[data_off + u32(e + 8):data_off + u32(e + 8) + u32(e + 12)]
    return out


def iso_file(iso, path):
    with open(iso, "rb") as f:
        head = f.read(0x440)
        fst_off, fst_size = struct.unpack(">II", head[0x424:0x42C])
        f.seek(fst_off)
        fst = f.read(fst_size)
        count = struct.unpack(">I", fst[8:12])[0]
        strtab = count * 12
        stack, i = [("", count)], 1
        while i < count:
            while stack and i >= stack[-1][1]:
                stack.pop()
            fn, off, size = struct.unpack(">III", fst[i * 12:i * 12 + 12])
            name_o = fn & 0xFFFFFF
            name = fst[strtab + name_o:fst.index(b"\0", strtab + name_o)].decode("latin1")
            p = (stack[-1][0] if stack else "") + name
            if fn >> 24:
                stack.append((p + "/", size))
            elif p == path:
                f.seek(off)
                return f.read(size)
            i += 1
    raise KeyError(path)


def decode_bti(b):
    fmt, w, h = b[0], struct.unpack(">H", b[2:4])[0], struct.unpack(">H", b[4:6])[0]
    off = struct.unpack(">I", b[0x1C:0x20])[0]
    d = b[off:]
    img = np.zeros((h, w, 4), np.float32)
    if fmt == 5:                                   # RGB5A3, 4x4 tiles
        k = 0
        for ty in range(0, h, 4):
            for tx in range(0, w, 4):
                for y in range(4):
                    for x in range(4):
                        v = struct.unpack(">H", d[k:k + 2])[0]
                        k += 2
                        if v & 0x8000:
                            r, g, bb, a = (v >> 10 & 31) * 255 / 31, (v >> 5 & 31) * 255 / 31, (v & 31) * 255 / 31, 255
                        else:
                            a = (v >> 12 & 7) * 255 / 7
                            r, g, bb = (v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17
                        if ty + y < h and tx + x < w:
                            img[ty + y, tx + x] = (r, g, bb, a)
    elif fmt == 2:                                 # IA4, 8x4 tiles
        k = 0
        for ty in range(0, h, 4):
            for tx in range(0, w, 8):
                for y in range(4):
                    for x in range(8):
                        v = d[k]
                        k += 1
                        i, a = (v & 15) * 17, (v >> 4) * 17
                        if ty + y < h and tx + x < w:
                            img[ty + y, tx + x] = (i, i, i, a)
    else:
        raise ValueError(f"texture format {fmt}")
    return img / 255.0


def blo_panes(b):
    """{tag: (x0, y0, x1, y1)} global rects of the root's direct picture children (no parent transform)."""
    out = {}
    o = 0x20
    while o < len(b):
        m, sz = b[o:o + 4], struct.unpack(">I", b[o + 4:o + 8])[0]
        if sz == 0:
            break
        if m == b"PIC2":
            p = b[o + 8:o + 8 + 0x48]
            base = p[13]
            tag = p[16:24].lstrip(b"\0").decode("latin1")
            w, h, sx, sy, ax, ay, az, ox, oy = struct.unpack(">9f", p[32:68])
            rx = (0, w / 2, w)[base % 3]
            ry = (0, h / 2, h)[base // 3]
            out[tag] = (ox - rx, oy - ry, ox - rx + w, oy - ry + h)
        o += sz
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso")
    ap.add_argument("--out", default=os.path.join("data", "game", "dive_sprites.npz"))
    a = ap.parse_args()
    arc = rarc(yaz0(iso_file(a.iso, "new_screen/eng/res_challengeSelect.szs")))
    panes = blo_panes(arc["challengemodo_select.blo"])
    flower = decode_bti(arc["flower_icon.bti"])
    out = {}
    for name, k in COLS:
        p0 = panes["Pw_pk_r" if k == "w" else f"P{k}_pk_l"]
        p1 = panes["PICT_020" if k == "w" else f"P{k}_pk_r"]
        p2 = panes[f"P{k}_fw"]
        # J2D's "bottom" vertices are the ones at the smaller y (y grows down the screen)
        start = np.array([p0[0], p0[1]])                 # pane0 GLBVTX_BtmLeft
        vec0 = start - np.array([p1[2], p1[1]])          # pane0 BtmLeft - pane1 BtmRight
        vec1 = start - np.array([p2[0], p2[1]])          # pane0 BtmLeft - pane2 BtmLeft
        w1, h1 = p1[2] - p1[0], p1[3] - p1[1]
        w2, h2 = p2[2] - p2[0], p2[3] - p2[1]
        body = decode_bti(arc[f"new_{k}_pikmin.bti"])[:, ::-1].copy()     # drawn with negative width
        fl = flower.copy()
        if name in ("white", "purple"):                  # TEV: lerp(C0 = magenta, C1 = white, texture)
            c0 = np.array([1.0, 0.0, 1.0])
            fl[..., :3] = c0 + (1 - c0) * fl[..., :3]
        out[f"{name}_body"] = body
        out[f"{name}_body_rect"] = np.array([-vec0[0] - w1, -vec0[1], -vec0[0], -vec0[1] + h1])
        out[f"{name}_flower"] = fl
        out[f"{name}_flower_rect"] = np.array([-vec1[0], -vec1[1], -vec1[0] + w2, -vec1[1] + h2])
        out[f"{name}_start"] = start
        print(name, "start", start, "body", out[f"{name}_body_rect"], body.shape, "flower", out[f"{name}_flower_rect"])
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    np.savez(a.out, **out)
    print("wrote", a.out)


if __name__ == "__main__":
    sys.exit(main())
