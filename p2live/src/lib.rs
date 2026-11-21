//! Pikmin 2 sublevel seeds from the falling cave-name letters: a Rust port of p2seeds' detector
//! (see docs/realtime-obs.md). The Python pipeline in p2seeds/ is the reference; `p2live entries`
//! checks this port against a run's seeds.json.

pub mod analyze;
pub mod calibrate;
pub mod digits;
pub mod fit;
pub mod img;
pub mod lattice;
pub mod rng;
pub mod templates;
pub mod track;
pub mod video;
