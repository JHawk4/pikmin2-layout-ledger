//! pod2: the Pay Off Debt judge, rebuilt from the old one's parts.
//!
//! `parts()` recomputes CaveGen's pod score for one choice of which counted treasures the
//! runner takes (the old judge always takes them all), and adds terms the old judge lacks
//! (water to cross, the hole route, bug pokos kept apart). `judge()` combines those parts
//! with the fitted weights in `MODEL` and lets the runner skip a treasure when skipping
//! scores better (see judge2/LOG.md for how each piece was chosen and validated).

use cavegen3::Layout;
use serde_json::{Value, json};

use crate::features::{route, water_rects};
use crate::graph::Graph;
use crate::old_judge::{Ctx, JhawkJudge, Placed, carry_info, difficulty, names, pokos};

pub struct Pod2 {
    pub total: f64,
    pub parts: Value,
}

pub(crate) fn ctx<'a>(j: &'a JhawkJudge, layout: &Layout) -> Ctx<'a> {
    let placed = Placed::from_layout(layout);
    let start_pos = placed.sps[placed.start].pos;
    let graph = Graph::build(layout, start_pos);
    Ctx { j, p: placed, g: graph }
}

/// Seconds (except where noted) for one take/skip choice.
#[derive(Debug, Clone, Default)]
pub struct Parts {
    pub walking: f64,
    pub carry: f64,
    pub hazard: f64,
    pub gate: f64,
    pub optional: f64,
    /// (expected pokos - pokos of the taken treasures) / 2
    pub poko: f64,
    /// bug pokos / 2 (the old judge subtracts this inside its poko term)
    pub bug: f64,
    pub adj: f64,
    pub taken: i32,
    /// cm of water the taken treasures' carry routes must cross (not counting a starting pool)
    pub water_carry: f64,
    /// the same for the most watery single taken treasure route
    pub water_carry_max: f64,
    /// cm of water to cross on the route between the ship and the hole
    pub water_hole: f64,
    /// seconds to walk from the ship to the hole (whole route)
    pub hole_walk: f64,
    /// gate seconds on the hole's own route
    pub gate_hole: f64,
    /// fight seconds of teki carrying a taken treasure
    pub carrier_fight: f64,
    /// names of the skipped counted treasures
    pub skipped: Vec<String>,
    /// the hole's share of `walking`: hole distance / speed / (1 + taken)
    pub hole_part: f64,
    /// hazard seconds by teki name
    pub haz_by: std::collections::BTreeMap<String, f64>,
    /// hazard seconds of teki in the way of the hole route only (not of a taken treasure)
    pub hazard_hole: f64,
    /// SH-6: water the lens (bey_goma) carry route must cross, if it is taken
    pub lens_cross: f64,
}

impl Parts {
    /// The old judge's score for this choice.
    pub fn old_total(&self) -> f64 {
        self.walking + self.carry + self.hazard + self.gate + self.optional + self.poko - self.bug + self.adj + 10.0 * self.taken as f64
    }

    pub fn to_json(&self) -> Value {
        json!({
            "walking": self.walking, "carry": self.carry, "hazard": self.hazard, "gate": self.gate,
            "optional": self.optional, "poko": self.poko, "bug": self.bug, "adj": self.adj, "taken": self.taken,
            "water_carry": self.water_carry, "water_carry_max": self.water_carry_max, "water_hole": self.water_hole,
            "hole_walk": self.hole_walk, "gate_hole": self.gate_hole, "carrier_fight": self.carrier_fight,
            "skipped": self.skipped, "hole_part": self.hole_part, "haz_by": self.haz_by, "hazard_hole": self.hazard_hole, "lens_cross": self.lens_cross,
        })
    }
}

/// The counted (non-ignored, non-optional) treasures: (name, spawn point, dig?, carrier).
fn counted(c: &Ctx) -> Vec<(String, usize, bool, Option<String>)> {
    let n = names();
    c.p.items
        .iter()
        .map(|i| (i.name.to_ascii_lowercase(), i.sp, true, None))
        .chain(c.p.tekis.iter().filter_map(|t| t.item_inside.as_ref().map(|nm| (nm.to_ascii_lowercase(), t.sp, false, Some(t.name.clone())))))
        .filter(|(name, ..)| !n.ignore_treasures_pod.contains(name.as_str()) && !n.optional_treasures_pod.contains(name.as_str()))
        .collect()
}

/// The old judge's pod score, split into parts, when the counted treasures with `skip[i]`
/// set are left behind. With no skips the parts sum to the old score exactly (f32 aside).
pub fn parts(j: &JhawkJudge, layout: &Layout, skip: &[bool]) -> Parts {
    let mut c = ctx(j, layout);
    let n = names();
    let rects = water_rects(layout);
    let all = counted(&c);
    let take: Vec<&(String, usize, bool, Option<String>)> =
        all.iter().enumerate().filter(|(i, _)| !skip.get(*i).copied().unwrap_or(false)).map(|(_, t)| t).collect();
    let mut out = Parts { skipped: all.iter().enumerate().filter(|(i, _)| skip.get(*i).copied().unwrap_or(false)).map(|(_, t)| t.0.clone()).collect(), ..Default::default() };

    let num_treasures_collected = take.len() as i32;
    let num_pokos_collected: i32 = take.iter().map(|t| pokos(&t.0)).sum();
    let targets: Vec<usize> = take.iter().map(|t| t.1).collect();

    // carry
    let mut pikmin_seconds = 0.0f32;
    let mut active_pikmin = 0.0f32;
    for (name, sp, dig, carrier) in take.iter() {
        c.mark(*sp);
        active_pikmin += carry_info(name).max_carry as f32;
        pikmin_seconds += j.story_carry(&mut c, name, *sp, *dig, j.piki_carry_value);
        let p = c.sp_pos(*sp);
        let r = route(&mut c, &rects, p);
        out.water_carry += r.cross as f64;
        out.water_carry_max = out.water_carry_max.max(r.cross as f64);
        if name == "bey_goma" {
            out.lens_cross = r.cross as f64;
        }
        if let Some(t) = carrier {
            out.carrier_fight += difficulty(t).sec as f64;
        }
    }
    let carry_seconds = if pikmin_seconds == 0.0 { 0.0 } else { pikmin_seconds / (j.piki_count as f32).min(active_pikmin) };

    let mut walking_seconds = c.walking_mst(&targets);
    let hole = c.p.hole.or(c.p.geyser);
    if let Some(h) = hole {
        let d = c.dist_to_start(h);
        walking_seconds += d / j.olimar_speed_cm / (1 + num_treasures_collected) as f32;
        out.hole_part = (d / j.olimar_speed_cm / (1 + num_treasures_collected) as f32) as f64;
        out.hole_walk = (d / j.olimar_speed_cm) as f64;
        let p = c.sp_pos(h);
        out.water_hole = route(&mut c, &rects, p).cross as f64;
    } else {
        walking_seconds += 300.0;
    }

    // teki in the way, bug pokos
    let mut hazard_seconds = 0.0f32;
    let mut bug_pokos = 0;
    c.compute_carryable("");
    for t in 0..c.p.tekis.len() {
        if c.teki_in_the_way(t) {
            let name = c.p.tekis[t].name.to_ascii_lowercase();
            hazard_seconds += difficulty(&name).sec as f32 / 2.0;
            *out.haz_by.entry(name.clone()).or_insert(0.0) += difficulty(&name).sec as f64 / 2.0;
            let sp = c.p.tekis[t].sp;
            if !n.no_carcass.contains(name.as_str()) && c.dist_to_start(sp) / j.olimar_speed_cm < walking_seconds * 0.4 {
                bug_pokos += pokos(&name);
            }
        }
    }

    // optional treasures: exactly as the old judge
    let mut optional_seconds = 0.0f32;
    let dig_divisor = (j.piki_count / (num_treasures_collected + 1)) as f32;
    for k in 0..c.p.items.len() {
        let (name, sp) = (c.p.items[k].name.to_ascii_lowercase(), c.p.items[k].sp);
        if !n.optional_treasures_pod.contains(name.as_str()) {
            continue;
        }
        let info = carry_info(&name);
        let dig = c.dig_time(&name);
        let min_dist_visited = JhawkJudge::min_dist_to_visited(&c, sp, true);
        let mut gate_check = 0.0f32;
        if !c.p.gates.is_empty() && c.p.sps[sp].is_alcove {
            if let Some(door) = c.p.first_door_pos[c.p.sps[sp].unit.unwrap()] {
                for g in c.p.gates.iter() {
                    let gp = c.sp_pos(g.sp);
                    if gp.x == door.x && gp.z == door.z {
                        gate_check += c.gate_cost(g.life, j.piki_count as f32);
                    }
                }
            }
        }
        let carry_value = if j.cave_short_name == "FC" && j.floor == 6 { 2.4 } else { j.piki_carry_value };
        let d = c.dist_to_start(sp);
        let time_needed = 10.0
            + 2.0 * min_dist_visited / j.olimar_speed_cm
            + 3.0
            + dig / dig_divisor
            + gate_check
            + d * 8.5 / Ctx::carry_speed(carry_value, info.max_carry, info.min_carry, info.max_carry);
        optional_seconds -= JhawkJudge::optional_time_save(pokos(&name), time_needed);
    }
    for k in 0..c.p.tekis.len() {
        let Some(name) = c.p.tekis[k].item_inside.as_ref().map(|nm| nm.to_ascii_lowercase()) else { continue };
        if !n.optional_treasures_pod.contains(name.as_str()) {
            continue;
        }
        let (teki_name, sp) = (c.p.tekis[k].name.clone(), c.p.tekis[k].sp);
        let info = carry_info(&name);
        let min_dist_visited = JhawkJudge::min_dist_to_visited(&c, sp, false);
        let d = c.dist_to_start(sp);
        let time_needed = 10.0
            + difficulty(&teki_name).sec as f32
            + 2.0 * min_dist_visited / j.olimar_speed_cm
            + 3.0
            + 0.0 / dig_divisor
            + d * 8.5 / Ctx::carry_speed(j.piki_carry_value, info.max_carry, info.min_carry, info.max_carry);
        optional_seconds -= JhawkJudge::optional_time_save(pokos(&name), time_needed);
    }

    // teki in the way of the hole route only
    if hole.is_some() {
        let before: Vec<bool> = (0..c.p.tekis.len()).map(|t| c.teki_in_the_way(t)).collect();
        c.compute_carryable("h");
        for t in 0..c.p.tekis.len() {
            if !before[t] && c.teki_in_the_way(t) {
                let name = c.p.tekis[t].name.to_ascii_lowercase();
                out.hazard_hole += difficulty(&name).sec as f64 / 2.0;
            }
        }
    }

    // gates on the routes of the taken treasures and the hole
    let mut gate_seconds = 0.0f32;
    if !c.p.gates.is_empty() {
        c.compute_carryable("h");
        for g in 0..c.p.gates.len() {
            if c.gate_in_the_way(g) {
                gate_seconds += c.gate_cost(c.p.gates[g].life, j.piki_count as f32);
            }
        }
        // the hole's own route
        if let Some(h) = hole {
            let p = c.sp_pos(h);
            let r = route(&mut c, &rects, p);
            for g in crate::features::gates_on(&mut c, &r.wps) {
                out.gate_hole += c.gate_cost(c.p.gates[g].life, j.piki_count as f32) as f64;
            }
        }
    }

    // GK adjustments, as the old judge (high treasures and breadbugs only for taken ones)
    let mut adj_seconds = 0.0f32;
    if j.cave_short_name == "GK" {
        if j.floor == 2 {
            for i in c.p.items.iter() {
                if i.name.eq_ignore_ascii_case("g_futa_kyusyu") && !out.skipped.iter().any(|s| s == "g_futa_kyusyu") {
                    let idx = c.p.sps[i.sp].list_idx;
                    if idx == 6 || idx == 7 {
                        walking_seconds = 4.0;
                    }
                }
            }
            hazard_seconds = 0.0;
            out.haz_by.clear();
        }
        let taken_sps: Vec<usize> = take.iter().map(|t| t.1).collect();
        for i in c.p.items.iter() {
            if n.ignore_treasures_pod.contains(i.name.to_ascii_lowercase().as_str()) {
                continue;
            }
            if !taken_sps.contains(&i.sp) && !n.optional_treasures_pod.contains(i.name.to_ascii_lowercase().as_str()) {
                continue;
            }
            let y = c.sp_pos(i.sp).y;
            if y == 100.0 || y == 125.0 {
                adj_seconds += 12.0;
            }
        }
        for ii in 0..c.p.items.len() {
            let name = c.p.items[ii].name.to_ascii_lowercase();
            let isp = c.p.items[ii].sp;
            if n.ignore_treasures_pod.contains(name.as_str()) {
                continue;
            }
            if !taken_sps.contains(&isp) && !n.optional_treasures_pod.contains(name.as_str()) {
                continue;
            }
            if c.sp_pos(isp).y >= 30.0 || carry_info(&name).min_carry > 10 {
                continue;
            }
            let d_item = c.dist_to_start(isp);
            if d_item < 170.0 {
                continue;
            }
            let mut worst = 0.0f32;
            for t in c.p.tekis.iter() {
                if t.name.eq_ignore_ascii_case("panmodoki") {
                    let closeness = c.sp_dist(t.sp, isp) / d_item;
                    if closeness < 0.25 {
                        worst = worst.max((1.5 / closeness).min(15.0));
                    }
                }
            }
            adj_seconds += worst;
        }
    }

    out.walking = walking_seconds as f64;
    out.carry = carry_seconds as f64;
    out.hazard = hazard_seconds as f64;
    out.gate = gate_seconds as f64;
    out.optional = optional_seconds as f64;
    out.poko = (j.expected_num_pokos_pod - num_pokos_collected) as f64 / 2.0;
    out.bug = bug_pokos as f64 / 2.0;
    out.adj = adj_seconds as f64;
    out.taken = num_treasures_collected;
    out
}

/// Every take/skip choice worth considering: all subsets for up to 4 counted treasures,
/// otherwise taking all and skipping each one alone.
pub fn variants(j: &JhawkJudge, layout: &Layout) -> Vec<Parts> {
    let c = ctx(j, layout);
    let k = counted(&c).len();
    let masks: Vec<Vec<bool>> = if k <= 4 {
        (0..1u32 << k).map(|m| (0..k).map(|i| m >> i & 1 == 1).collect()).collect()
    } else {
        std::iter::once(vec![false; k]).chain((0..k).map(|i| (0..k).map(|x| x == i).collect())).collect()
    };
    masks.iter().map(|m| parts(j, layout, m)).collect()
}

/// The fitted model (judge2/LOG.md, "final"). Weights were fitted in-sample and validated
/// out of sample; the poko term keeps weight 1 because the outcome counts 2 pokos per second.
pub struct Model {
    pub walking: f64,
    pub carry: f64,
    pub hazard: f64,
    pub gate: f64,
    /// optional-treasure credit (runners almost never collect them)
    pub optional: f64,
    /// bug-poko credit (the outcome never counts bug pokos)
    pub bug: f64,
    /// Glutton's Kitchen adjustments (high treasures, breadbugs)
    pub adj: f64,
    /// seconds per collected treasure (cutscene and panel)
    pub per_treasure: f64,
    /// SH-6: taking the lens when its carry route crosses water (in practice: it is skipped)
    pub lens_water: f64,
    /// how sure the runner's take/skip choice is: choices are weighted by exp(-score / temp)
    pub temp: f64,
}

pub const MODEL: Model = Model {
    walking: 1.22,
    carry: 0.78,
    hazard: 0.60,
    gate: 0.58,
    optional: 0.0,
    bug: 0.0,
    adj: 0.54,
    per_treasure: 10.0,
    lens_water: 100.0,
    temp: 5.0,
};

impl Model {
    pub fn score(&self, v: &Parts) -> f64 {
        self.walking * v.walking
            + self.carry * v.carry
            + self.hazard * v.hazard
            + self.gate * v.gate
            + self.optional * v.optional
            + v.poko
            - self.bug * v.bug
            + self.adj * v.adj
            + self.per_treasure * v.taken as f64
            + if v.lens_cross > 0.0 { self.lens_water } else { 0.0 }
    }
}

/// judge2's Pay Off Debt score: the expected net seconds over the runner's take/skip choices.
pub fn judge(j: &JhawkJudge, layout: &Layout) -> Pod2 {
    let vs = variants(j, layout);
    let m = &MODEL;
    let scores: Vec<f64> = vs.iter().map(|v| m.score(v)).collect();
    let best = scores.iter().cloned().fold(f64::INFINITY, f64::min);
    let w: Vec<f64> = scores.iter().map(|s| (-(s - best) / m.temp).exp()).collect();
    let wsum: f64 = w.iter().sum();
    let total = scores.iter().zip(&w).map(|(s, w)| s * w).sum::<f64>() / wsum;
    let choices: Vec<Value> = vs
        .iter()
        .zip(&scores)
        .zip(&w)
        .map(|((v, s), w)| json!({"skip": v.skipped, "score": (s * 100.0).round() / 100.0, "p": (w / wsum * 1000.0).round() / 1000.0}))
        .collect();
    let v0 = &vs[0];
    Pod2 {
        total,
        parts: json!({
            "all_taken": {
                "walking": m.walking * v0.walking, "carry": m.carry * v0.carry, "hazard": m.hazard * v0.hazard,
                "gate": m.gate * v0.gate, "adj": m.adj * v0.adj, "treasures": m.per_treasure * v0.taken as f64,
                "poko": v0.poko, "lens_water": if v0.lens_cross > 0.0 { m.lens_water } else { 0.0 },
            },
            "choices": choices,
        }),
    }
}

pub fn dump(j: &JhawkJudge, layout: &Layout) -> Value {
    let mut c = ctx(j, layout);
    let mut v = crate::features::dump(&mut c, layout);
    v["variants"] = Value::Array(variants(j, layout).iter().map(|p| p.to_json()).collect());
    v
}
