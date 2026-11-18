//! Geometry of one layout, as plain numbers for analysis and for the pod2 judge.
//!
//! Everything is measured on CaveGen's waypoint graph (the carry-path tree rooted at the
//! ship): `dist` is the carry/walk distance to the ship along that tree, `path` is the list of
//! waypoints from an object to the ship, and the tree distance between two objects goes
//! through their lowest common ancestor. Water is the union of the map units' waterboxes
//! (in the XZ plane).

use std::collections::HashSet;

use cavegen3::layout::Layout;
use serde_json::{Value, json};

use crate::graph::{V3, dist};
use crate::old_judge::{Ctx, carry_info, difficulty, names, pokos};

/// Axis-aligned water rectangles in game coordinates: (x1, z1, x2, z2).
pub(crate) fn water_rects(layout: &Layout) -> Vec<(f32, f32, f32, f32)> {
    let mut out = Vec::new();
    for u in layout.units.iter() {
        let cx = (u.x as f32 + u.unit.width as f32 / 2.0) * 170.0;
        let cz = (u.z as f32 + u.unit.height as f32 / 2.0) * 170.0;
        for w in u.unit.waterboxes.iter() {
            out.push((cx + w.p1[0], cz + w.p1[2], cx + w.p2[0], cz + w.p2[2]));
        }
    }
    out
}

pub(crate) fn in_water(rects: &[(f32, f32, f32, f32)], x: f32, z: f32) -> bool {
    rects.iter().any(|&(x1, z1, x2, z2)| x >= x1 && x <= x2 && z >= z1 && z <= z2)
}

/// Length of the segment a-b that lies in water (sampled every ~10 units).
pub(crate) fn water_len(rects: &[(f32, f32, f32, f32)], a: V3, b: V3) -> f32 {
    if rects.is_empty() {
        return 0.0;
    }
    let len = dist(a, b);
    let n = ((len / 10.0).ceil() as usize).max(1);
    let mut wet = 0;
    for i in 0..n {
        let t = (i as f32 + 0.5) / n as f32;
        if in_water(rects, a.x + (b.x - a.x) * t, a.z + (b.z - a.z) * t) {
            wet += 1;
        }
    }
    len * wet as f32 / n as f32
}

/// The route from a point to the ship: closest waypoint, then back pointers.
pub(crate) fn path_wps(c: &mut Ctx, p: V3) -> Vec<usize> {
    let mut out = Vec::new();
    let Some(mut w) = c.g.closest_wp(p) else { return out };
    loop {
        out.push(w);
        if c.g.wps[w].is_start {
            break;
        }
        match c.g.wps[w].back {
            Some(b) if !out.contains(&b) => w = b,
            _ => break,
        }
    }
    out
}

pub(crate) struct Route {
    pub dist: f32,
    /// Water along the whole route.
    pub water: f32,
    /// Water after the route's first dry stretch: water that must be crossed, not just the
    /// pool the object starts in (a teki can be lured out of it; a carrier walks out of it).
    pub cross: f32,
    pub wps: Vec<usize>,
}

pub(crate) fn route(c: &mut Ctx, rects: &[(f32, f32, f32, f32)], p: V3) -> Route {
    let wps = path_wps(c, p);
    let d = c.g.dist_to_start(p);
    let (mut water, mut cross, mut dry) = (0.0f32, 0.0f32, false);
    let mut prev = p;
    for &w in wps.iter() {
        let q = c.g.wps[w].pos;
        let len = dist(prev, q);
        let n = ((len / 10.0).ceil() as usize).max(1);
        for i in 0..n {
            let t = (i as f32 + 0.5) / n as f32;
            if !rects.is_empty() && in_water(rects, prev.x + (q.x - prev.x) * t, prev.z + (q.z - prev.z) * t) {
                water += len / n as f32;
                if dry {
                    cross += len / n as f32;
                }
            } else {
                dry = true;
            }
        }
        prev = q;
    }
    Route { dist: d, water, cross, wps }
}

/// Tree distance between two routes: the part of each route not shared with the other.
/// Returns (distance a->b, length of a's route not shared with b's route).
pub(crate) fn tree_between(c: &Ctx, a: &Route, b: &Route) -> (f32, f32) {
    let bset: HashSet<usize> = b.wps.iter().copied().collect();
    // first waypoint of a's route that is on b's route
    let lca = a.wps.iter().copied().find(|w| bset.contains(w));
    match lca {
        Some(l) => {
            let dl = c.g.wps[l].dist_to_start;
            let a_off = (a.dist - dl).max(0.0);
            let b_off = (b.dist - dl).max(0.0);
            (a_off + b_off, a_off)
        }
        None => (a.dist + b.dist, a.dist),
    }
}

/// Water length on the part of a's route that is not on b's route.
pub(crate) fn water_off(c: &Ctx, rects: &[(f32, f32, f32, f32)], p: V3, a: &Route, b: &Route) -> f32 {
    let bset: HashSet<usize> = b.wps.iter().copied().collect();
    let mut water = 0.0;
    let mut prev = p;
    for &w in a.wps.iter() {
        let q = c.g.wps[w].pos;
        water += water_len(rects, prev, q);
        if bset.contains(&w) {
            break;
        }
        prev = q;
    }
    water
}

fn r1(v: f32) -> f64 {
    ((v as f64) * 10.0).round() / 10.0
}

/// Every treasure, gate, teki and the hole with its geometry.
pub(crate) fn dump(c: &mut Ctx, layout: &Layout) -> Value {
    let n = names();
    let rects = water_rects(layout);
    let speed = c.j.olimar_speed_cm;
    let hole_sp = c.p.hole.or(c.p.geyser);
    let hole_route = hole_sp.map(|h| {
        let p = c.sp_pos(h);
        route(c, &rects, p)
    });
    let hole_json = match (&hole_route, hole_sp) {
        (Some(r), Some(h)) => {
            let p = c.sp_pos(h);
            let gates: Vec<f64> = gates_on(c, &r.wps).into_iter().map(|g| c.p.gates[g].life as f64).collect();
            json!({"x": r1(p.x), "z": r1(p.z), "dist": r1(r.dist), "water": r1(r.water), "cross": r1(r.cross), "gates": gates,
                   "in_water": in_water(&rects, p.x, p.z), "alcove": c.p.sps[h].is_alcove, "geyser": c.p.hole.is_none()})
        }
        _ => Value::Null,
    };

    let mut treasures = Vec::new();
    let items: Vec<(String, usize, Option<String>, V3)> = c
        .p
        .items
        .iter()
        .map(|i| (i.name.to_ascii_lowercase(), i.sp, None, c.p.sps[i.sp].pos))
        .chain(c.p.tekis.iter().filter_map(|t| t.item_inside.as_ref().map(|nm| (nm.to_ascii_lowercase(), t.sp, Some(t.name.clone()), t.pos))))
        .collect();
    for (name, sp, carrier, _pos) in items {
        let p = c.sp_pos(sp);
        let r = route(c, &rects, p);
        let info = carry_info(&name);
        let (to_hole, off_hole, water_off_hole) = match &hole_route {
            Some(h) => {
                let (tb, off) = tree_between(c, &r, h);
                (tb, off, water_off(c, &rects, p, &r, h))
            }
            None => (r.dist, r.dist, r.water),
        };
        let gates: Vec<f64> = gates_on(c, &r.wps).into_iter().map(|g| c.p.gates[g].life as f64).collect();
        let j = c.j;
        let story = j.story_carry(c, &name, sp, carrier.is_none(), j.piki_carry_value);
        let kind = if n.ignore_treasures_pod.contains(name.as_str()) {
            "ignored"
        } else if n.optional_treasures_pod.contains(name.as_str()) {
            "optional"
        } else {
            "counted"
        };
        treasures.push(json!({
            "name": name, "kind": kind, "pokos": pokos(&name), "min_carry": info.min_carry, "max_carry": info.max_carry,
            "carried_by": carrier, "teki_sec": carrier.as_ref().map(|t| difficulty(t).sec),
            "dig": c.dig_time(&name), "depth": info.depth,
            "x": r1(p.x), "y": r1(p.y), "z": r1(p.z), "dist": r1(r.dist), "water": r1(r.water), "cross": r1(r.cross),
            "in_water": in_water(&rects, p.x, p.z), "alcove": c.p.sps[sp].is_alcove,
            "to_hole": r1(to_hole), "off_hole": r1(off_hole), "water_off_hole": r1(water_off_hole),
            "gates": gates,
            "story_carry": r1(story),
        }));
    }

    // teki: in the way of the counted treasures' carry paths (as the old judge marks them)
    // Per teki, against every treasure (in `treasures` order) and the hole:
    //   off_tre[i]: tree distance from the teki off treasure i's route (its detour, one way)
    //   near_tre[i]: straight-line distance from the teki to treasure i's route polyline
    //   near_hole: the same for the ship-hole route
    let tre_routes: Vec<(V3, Route)> = c
        .p
        .items
        .iter()
        .map(|i| i.sp)
        .chain(c.p.tekis.iter().filter(|t| t.item_inside.is_some()).map(|t| t.sp))
        .collect::<Vec<_>>()
        .into_iter()
        .map(|sp| {
            let p = c.sp_pos(sp);
            (p, route(c, &rects, p))
        })
        .collect();
    let hole_pos = hole_sp.map(|h| c.sp_pos(h));
    let mut tekis = Vec::new();
    for t in 0..c.p.tekis.len() {
        let tk = c.p.tekis[t].clone();
        let name = tk.name.to_ascii_lowercase();
        let d = difficulty(&name);
        let td = c.dist_to_start(tk.sp);
        let rt = route(c, &rects, tk.pos);
        let off_hole = match &hole_route {
            Some(h) => tree_between(c, &rt, h).1,
            None => td,
        };
        let off_tre: Vec<f64> = tre_routes.iter().map(|(_, r)| r1(tree_between(c, &rt, r).1)).collect();
        let near_tre: Vec<f64> = tre_routes.iter().map(|(p, r)| r1(near_route(c, tk.pos, *p, r))).collect();
        let near_hole = match (&hole_route, hole_pos) {
            (Some(h), Some(hp)) => r1(near_route(c, tk.pos, hp, h)),
            _ => -1.0,
        };
        tekis.push(json!({"name": tk.name, "carrying": tk.item_inside, "sec": d.sec, "piki": d.piki,
            "carcass": !n.no_carcass.contains(name.as_str()), "pokos": pokos(&name),
            "dist": r1(td), "off_hole": r1(off_hole), "x": r1(tk.pos.x), "z": r1(tk.pos.z),
            "in_water": in_water(&rects, tk.pos.x, tk.pos.z), "seam": c.p.sps[tk.sp].unit.is_none(),
            "off_tre": off_tre, "near_tre": near_tre, "near_hole": near_hole}));
    }

    let gates: Vec<Value> = c
        .p
        .gates
        .iter()
        .map(|g| {
            let p = c.p.sps[g.sp].pos;
            json!({"life": g.life, "x": r1(p.x), "z": r1(p.z)})
        })
        .collect();

    json!({
        "speed": speed, "units": layout.units.len(), "water_area": rects.iter().map(|r| ((r.2 - r.0) * (r.3 - r.1)) as f64).sum::<f64>(),
        "hole": hole_json, "treasures": treasures, "tekis": tekis, "gates": gates,
    })
}

/// Straight-line distance from `q` to a route: the object at `start`, then its waypoints to the ship.
pub(crate) fn near_route(c: &mut Ctx, q: V3, start: V3, r: &Route) -> f32 {
    let mut best = dist(q, start);
    let mut prev = start;
    for &w in r.wps.iter() {
        let p = c.g.wps[w].pos;
        best = best.min(c.g.point_to_segment_dist(q, prev, p, 0.0, 0.0));
        prev = p;
    }
    best
}

/// Gates whose door lies on this route (the gate's closest waypoint is on it).
pub(crate) fn gates_on(c: &mut Ctx, wps: &[usize]) -> Vec<usize> {
    let set: HashSet<usize> = wps.iter().copied().collect();
    let mut out = Vec::new();
    for g in 0..c.p.gates.len() {
        let p = c.sp_pos(c.p.gates[g].sp);
        if let Some(w) = c.g.closest_wp(p) {
            if set.contains(&w) {
                out.push(g);
            }
        }
    }
    out
}
