//! Digit reads frame by frame: digit_scan VIDEO X0 Y0 X1 Y1 START STOP LANG
use p2live::analyze::Frames;
use p2live::digits::{digit_crop, read, split_digits};
use p2live::video::{probe, Feed, Window};
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let n = |i: usize| a[i].parse::<usize>().unwrap();
    let info = probe(&a[1]).unwrap();
    let feed = Feed { x0: n(2), y0: n(3), x1: n(4), y1: n(5) };
    let (s, e) = (n(6), n(7));
    let w = Window::new(&a[1], info.clone(), info.fps, feed, s, e).unwrap();
    for (i, g) in w.frames(s, e).iter().enumerate() {
        let c = digit_crop(g, &a[8]);
        let parts = c.as_ref().map(split_digits).unwrap_or_default();
        let (v, sc) = c.as_ref().map(read).unwrap_or((None, 0.0));
        let sum: u64 = g.row(g.h / 2).iter().map(|&x| x as u64).sum();
        println!("{} crop {:?} parts {} read {:?} {:.3} rowsum {}", s + i, c.as_ref().map(|c| (c.w, c.h)), parts.len(), v, sc, sum);
    }
}
#[allow(dead_code)]
pub fn dbg_band(g: &p2live::img::Gray) {
    let h = g.h;
    let (y0, y1) = ((0.46 * h as f64) as usize, (0.70 * h as f64) as usize);
    let p = p2live::img::prep(&g.crop(0, y0, g.w, y1), None);
    let on = |x: usize, y: usize| p.at(x, y) > 0.5;
    let rows: Vec<usize> = (0..p.h).filter(|&y| (0..p.w).filter(|&x| on(x, y)).count() as f64 / p.w as f64 > 0.01).collect();
    let cols: Vec<usize> = (0..p.w).filter(|&x| (0..p.h).any(|y| on(x, y))).collect();
    println!("{} {}x{} rows {:?}..{:?} cols {:?}", h, p.w, p.h, rows.first(), rows.last(), &cols[cols.len().saturating_sub(30)..]);
}
