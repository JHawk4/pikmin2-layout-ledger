use std::time::Instant;
use p2live::img::{prep, FftImage};
use p2live::video::{probe, decode, Feed};
use p2live::calibrate::{calibrate, compose};
use p2live::templates::caves;
fn main() {
    let v = "C:/Users/Jordan/Desktop/Claude/p2-vod-seeds/data/videos/01_JackDraz_mewq470m.mp4";
    let info = probe(v).unwrap();
    let feed = Feed { x0: 175, y0: 0, x1: 640, y1: 360 };
    let fr = decode(v, &info, 30.0, feed, 15126, 1).unwrap();
    let g = &fr[0];
    let cs = caves();
    let t = Instant::now();
    let c = calibrate(g, &cs).unwrap();
    println!("calibrate {:?} {} {:.3}", t.elapsed(), c.cave.cavegen, c.score);
    let p = prep(g, None);
    let region = p.rows((0.14 * p.h as f64) as usize, (0.48 * p.h as f64) as usize);
    println!("region {}x{}", region.w, region.h);
    let t = Instant::now();
    let fi = FftImage::new(region.clone());
    println!("fft image {:?}", t.elapsed());
    let t = Instant::now();
    let mut imgs = vec![];
    for _ in 0..50 { imgs.push(compose("Subterranean Complex", 0.7, 0.74, None).0); }
    println!("compose x50 {:?} ({}x{})", t.elapsed(), imgs[0].w, imgs[0].h);
    let t = Instant::now();
    for im in &imgs[..20] { let _ = fi.match_t(im); }
    println!("match_t x20 {:?}", t.elapsed());
}
