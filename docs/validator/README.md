# Validator tools for the Challenge Mode seed hunt

Independent checks of proposed floor seeds: different frames, different object classes, and the
seeds a few draws away. Set `P2SEEDS_LAYOUTMATCH` to a built `layoutmatch.exe`
(`docs/layout_matcher/build.sh`).

| tool | what it answers |
|---|---|
| `family.py SUB SEED [N]` | Do seeds within ±N draws share the layout? Compares objects in the pod's frame and lists what tells a neighbour apart. |
| `ransac_check.py MARKS.json SUB SEED` | On one frame, fit the camera from one class of marked objects (e.g. Glowcaps), then score another class the original read did not use (e.g. Bulborbs). Runs the same on control seeds from the draw window. |
| `affine_overlay.py FRAME SUB SEED MARKS OUT` | Draws a seed's objects on a near top-down frame through an affine map fitted from 3 or more hand marks. |
| `floor_offsets.py VIDEO SUB SEED F0,F1,F2 R0-R1` | Floor-shape score (`floor_check.py`'s scorer) of a seed and its ±40-draw neighbours on hand-picked comedown frames. |
| `dive_agree.py VIDEO DIVE.json SEED` | Dive-image loss of the dive state a layout seed implies, against random controls. Slow (about 8 min) and uninformative on the Wii record captures tried (CH8: at the control median). |
| `sheet.py VIDEO A B STEP OUT` | Contact sheet of labelled frames. |
| `board.py SUB SEED VERDICT "CHECKS"` | Sets the board row and appends the verdict in the shared hunt folder. |

Findings from the first round (the seven seeds already on pikmin-wrs):

- No seed has a near-identical neighbour within ±300 draws (at most 33–41% of objects shared, all
  of them fixed room features). Families come from far-apart seeds, not from neighbours.
- A one-draw shift changes the whole layout, so the "one draw late" risk of digit reads is settled
  by any feature outside the fixed pod room (CH28: the geyser).
- Comedown floor shape is uninformative on dark stages (CH28: |z| < 1 for every offset).
