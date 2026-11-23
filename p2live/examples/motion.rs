//! Per-frame entry-screen flag and name-band motion around a frame: motion VIDEO X0 Y0 X1 Y1 FRAME
use p2live::analyze::Frames;
use p2live::calibrate::is_entry_screen;
use p2live::video::{probe, Feed, Window};
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let n = |i: usize| a[i].parse::<usize>().unwrap();
    let info = probe(&a[1]).unwrap();
    let feed = Feed { x0: n(2), y0: n(3), x1: n(4), y1: n(5) };
    let f = n(6);
    let (s, e) = (f - 150, f + 60);
    let w = Window::new(&a[1], info.clone(), info.fps, feed, s, e).unwrap();
    let fr = w.frames(s, e);
    let mut run = 0;
    for i in 1..fr.len() {
        let g = &fr[i];
        let p = &fr[i - 1];
        let (y0, y1) = ((0.14 * g.h as f64) as usize, (0.48 * g.h as f64) as usize);
        let mut d = 0u64;
        let mut bright = 0u64;
        for y in y0..y1 {
            for (x, (&u, &v)) in g.row(y).iter().zip(p.row(y).iter()).enumerate() {
                let _ = x;
                if (u as i32 - v as i32).abs() > 24 { d += 1; }
                if u > 150 { bright += 1; }
            }
        }
        let flag = is_entry_screen(g);
        run = if flag { run + 1 } else { 0 };
        println!("{} {} run {:>3} moving {:>5} bright {:>5}", s + i, if flag { "E" } else { "." }, run, d, bright);
    }
}
