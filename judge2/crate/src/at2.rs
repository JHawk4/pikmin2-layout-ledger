//! at2: the All Treasures judge, CaveGen's `at` judge with its parts re-weighted on real
//! floor times (judge2/LOG_AT.md). Every treasure is collected, so there are no take/skip
//! choices and no pokos; what a layout costs is walking, carrying, enemies, gates, and two
//! quirks of the spawning: a treasure that is missing from the layout and purple candypops
//! (purple flowers) that are missing on sublevels where runners pick purples.

use cavegen3::Layout;
use serde_json::{Value, json};

use crate::old_judge::{AtParts, JhawkJudge};

pub struct Model {
    pub walking: f64,
    pub purple_walk: f64,
    pub carry: f64,
    pub hazard: f64,
    pub gate: f64,
    /// seconds per treasure on the layout (cutscene and collection)
    pub per_treasure: f64,
    /// seconds when any treasure is missing from the layout
    pub missing_treasure: f64,
    /// seconds per missing purple candypop
    pub missing_purple: f64,
}

/// Walking, carrying, enemies and gates take Pay Off Debt judge2's weights (pod2::MODEL, fitted on
/// 25 runs): on 189 All Treasures plays they come out calibrated (slope 0.95, CaveGen's own 0.77),
/// and 5 runs cannot tell finer weights apart (judge2/LOG_AT.md). Walking to purple candypops is
/// walking. The treasure count and the missing-treasure penalty keep CaveGen's values (no play so far
/// had a missing treasure). A missing purple candypop costs 10 s, not CaveGen's 60: the only two plays
/// with one (SR 5) put it at 5.5 ± 9.8 s, and 60 s would make the judge overstate layout differences
/// by 43% (LOG_AT.md). Sublevels where runners rely on the purples may cost more.
pub const MODEL: Model = Model {
    walking: 1.22,
    purple_walk: 1.22,
    carry: 0.78,
    hazard: 0.60,
    gate: 0.58,
    per_treasure: 10.0,
    missing_treasure: 300.0,
    missing_purple: 10.0,
};

impl Model {
    pub fn terms(&self, p: &AtParts) -> Value {
        json!({
            "walking": self.walking * (p.walking_seconds - p.purple_walk_seconds) as f64,
            "purple_walk": self.purple_walk * p.purple_walk_seconds as f64,
            "carry": self.carry * p.carry_seconds as f64,
            "hazard": self.hazard * p.hazard_seconds as f64,
            "gate": self.gate * p.gate_seconds as f64,
            "treasures": self.per_treasure * p.treasures as f64,
            "missing_treasure": if p.missing_treasures > 0 { self.missing_treasure } else { 0.0 },
            "missing_purple": self.missing_purple * p.missing_purples as f64,
        })
    }

    pub fn score(&self, p: &AtParts) -> f64 {
        self.walking * (p.walking_seconds - p.purple_walk_seconds) as f64
            + self.purple_walk * p.purple_walk_seconds as f64
            + self.carry * p.carry_seconds as f64
            + self.hazard * p.hazard_seconds as f64
            + self.gate * p.gate_seconds as f64
            + self.per_treasure * p.treasures as f64
            + if p.missing_treasures > 0 { self.missing_treasure } else { 0.0 }
            + self.missing_purple * p.missing_purples as f64
    }
}

pub fn raw(p: &AtParts) -> Value {
    json!({
        "walking": (p.walking_seconds - p.purple_walk_seconds) as f64, "purple_walk": p.purple_walk_seconds as f64,
        "carry": p.carry_seconds as f64, "hazard": p.hazard_seconds as f64, "gate": p.gate_seconds as f64,
        "treasures": p.treasures, "missing_treasures": p.missing_treasures, "missing_purples": p.missing_purples,
    })
}

pub fn judge(j: &JhawkJudge, layout: &Layout) -> (f64, Value) {
    let p = j.judge_at_parts(layout);
    (MODEL.score(&p), json!({ "terms": MODEL.terms(&p), "raw": raw(&p), "old": p.total() }))
}
