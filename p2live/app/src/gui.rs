//! The window: a four-step setup wizard, then the main view (the layout, the run so far, the
//! Browser Source link).

use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, Instant};

use eframe::egui::{self, Color32, ColorImage, Pos2, Rect, RichText, Sense, Stroke, StrokeKind, TextureHandle, TextureOptions, Vec2};

use crate::capture::{cameras, Crop, SourceSpec};
use crate::engine::{Cmd, DetectCfg, Engine, Entry};
use crate::server::{self, Overlay};
use crate::settings::{Category, Language, LayoutView, Profile, Settings};

const ACCENT: Color32 = Color32::from_rgb(255, 200, 60);
const GOOD: Color32 = Color32::from_rgb(120, 220, 120);
const WARN: Color32 = Color32::from_rgb(255, 170, 70);

pub struct App {
    engine: Engine,
    settings: Settings,
    overlay: Overlay,
    screen: Screen,
    preview: Option<(u64, TextureHandle, [usize; 2])>,
    layout: Option<(usize, u64, TextureHandle, [usize; 2])>,
    /// the entry shown large (None: the newest)
    selected: Option<usize>,
    toast: Option<(String, Instant)>,
    show_log: bool,
    /// the hint last saved to the profile
    saved_hint: Option<(f64, f64)>,
}

enum Screen {
    Wizard(Wizard),
    Main,
}

struct Wizard {
    step: usize,
    cameras: Vec<String>,
    source: Option<SourceSpec>,
    video_path: String,
    crop: Option<Crop>,
    /// the runner moved the crop: stop taking the detected one
    crop_edited: bool,
    frame_size: (usize, usize),
    category: Category,
    language: Language,
    name: String,
    /// editing this profile (else a new one)
    editing: Option<usize>,
    drag: Option<Handle>,
    seen_screens: usize,
}

#[derive(Clone, Copy, PartialEq)]
enum Handle {
    Corner(bool, bool),
    Move,
}

fn detect_cfg(p: &Profile) -> DetectCfg {
    DetectCfg { category: p.category, language: p.language, hint: p.hint, view: p.view.clone() }
}

impl App {
    pub fn new(cc: &eframe::CreationContext) -> App {
        let ctx = cc.egui_ctx.clone();
        let engine = Engine::start(Box::new(move || ctx.request_repaint()));
        let settings = Settings::load();
        let overlay = server::start(engine.shared.clone(), settings.port);
        let mut app = App { engine, settings, overlay, screen: Screen::Main, preview: None, layout: None, selected: None, toast: None, show_log: false, saved_hint: None };
        match app.settings.profile().cloned() {
            Some(p) => app.start_profile(&p),
            None => app.screen = Screen::Wizard(app.new_wizard(None)),
        }
        app
    }

    fn new_wizard(&self, editing: Option<usize>) -> Wizard {
        let cams = cameras();
        let p = editing.and_then(|i| self.settings.profiles.get(i));
        let source = p.map(|p| p.source.clone()).or_else(|| cams.first().map(|c| SourceSpec::Camera { name: c.clone() }));
        let video_path = match &source {
            Some(SourceSpec::Video { path }) => path.clone(),
            _ => String::new(),
        };
        if let Some(s) = &source {
            self.engine.send(Cmd::Detect(None));
            self.engine.send(Cmd::Source(Some(s.clone())));
        }
        Wizard {
            step: 0,
            cameras: cams,
            source,
            video_path,
            crop: p.map(|p| p.crop),
            crop_edited: p.is_some(),
            frame_size: p.map(|p| p.frame_size).unwrap_or((0, 0)),
            category: p.map(|p| p.category).unwrap_or(Category::Pod),
            language: p.map(|p| p.language).unwrap_or(Language::Auto),
            name: p.map(|p| p.name.clone()).unwrap_or_default(),
            editing,
            drag: None,
            seen_screens: 0,
        }
    }

    fn start_profile(&mut self, p: &Profile) {
        self.engine.send(Cmd::Source(Some(p.source.clone())));
        self.engine.send(Cmd::Crop(Some(p.crop)));
        self.engine.send(Cmd::Detect(Some(detect_cfg(p))));
        self.saved_hint = p.hint;
        self.screen = Screen::Main;
    }

    fn toast(&mut self, s: impl Into<String>) {
        self.toast = Some((s.into(), Instant::now()));
    }

    fn save(&mut self) {
        match self.settings.save() {
            Ok(_) => {}
            Err(e) => self.toast(format!("could not save the settings: {e}")),
        }
    }

    /// Keep the learned name scale in the profile, so the next session reads names fast at once.
    fn keep_hint(&mut self) {
        let h = *self.engine.shared.hint.lock().unwrap();
        if h.is_some() && h != self.saved_hint {
            if let Some(i) = self.settings.active {
                if let Some(p) = self.settings.profiles.get_mut(i) {
                    p.hint = h;
                    self.saved_hint = h;
                    self.save();
                }
            }
        }
    }

    fn preview_texture(&mut self, ctx: &egui::Context) -> Option<(TextureHandle, [usize; 2])> {
        let n = self.engine.shared.preview_n.load(Ordering::SeqCst);
        if self.preview.as_ref().is_none_or(|(seen, _, _)| *seen != n) {
            let frame = self.engine.shared.preview.lock().unwrap().clone();
            match frame {
                Some(f) => {
                    let img = ColorImage::from_rgb([f.w, f.h], &f.rgb);
                    match self.preview.as_mut() {
                        Some((seen, tex, size)) => {
                            tex.set(img, TextureOptions::LINEAR);
                            *seen = n;
                            *size = [f.w, f.h];
                        }
                        None => self.preview = Some((n, ctx.load_texture("preview", img, TextureOptions::LINEAR), [f.w, f.h])),
                    }
                }
                None => self.preview = None,
            }
        }
        self.preview.as_ref().map(|(_, t, s)| (t.clone(), *s))
    }

    fn layout_texture(&mut self, ctx: &egui::Context, e: &Entry) -> Option<(TextureHandle, [usize; 2])> {
        let png = e.png.as_ref()?;
        if self.layout.as_ref().is_none_or(|(k, v, _, _)| *k != e.key || *v != e.version) {
            let img = decode_png(png)?;
            let size = img.size;
            self.layout = Some((e.key, e.version, ctx.load_texture("layout", img, TextureOptions::LINEAR), size));
        }
        self.layout.as_ref().map(|(_, _, t, s)| (t.clone(), *s))
    }
}

fn decode_png(bytes: &[u8]) -> Option<ColorImage> {
    let mut dec = png::Decoder::new(std::io::Cursor::new(bytes));
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut r = dec.read_info().ok()?;
    let mut buf = vec![0u8; r.output_buffer_size()];
    let info = r.next_frame(&mut buf).ok()?;
    let (w, h) = (info.width as usize, info.height as usize);
    let data = &buf[..info.buffer_size()];
    Some(match info.color_type {
        png::ColorType::Rgba => ColorImage::from_rgba_unmultiplied([w, h], data),
        png::ColorType::Rgb => ColorImage::from_rgb([w, h], data),
        png::ColorType::GrayscaleAlpha => ColorImage::from_rgba_unmultiplied([w, h], &data.chunks(2).flat_map(|p| [p[0], p[0], p[0], p[1]]).collect::<Vec<_>>()),
        _ => ColorImage::from_rgb([w, h], &data.iter().flat_map(|&v| [v, v, v]).collect::<Vec<_>>()),
    })
}

/// The largest rect of aspect `size` inside `avail`, centred.
fn fit(avail: Rect, size: [usize; 2]) -> Rect {
    let (w, h) = (size[0].max(1) as f32, size[1].max(1) as f32);
    let s = (avail.width() / w).min(avail.height() / h);
    Rect::from_center_size(avail.center(), Vec2::new(w * s, h * s))
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        let mut wizard = match std::mem::replace(&mut self.screen, Screen::Main) {
            Screen::Wizard(w) => Some(w),
            Screen::Main => None,
        };
        match wizard.as_mut() {
            Some(w) => {
                if self.wizard_ui(ui, &ctx, w) {
                    wizard = None;
                }
            }
            None => self.main_ui(ui, &ctx),
        }
        if let Some(w) = wizard {
            self.screen = Screen::Wizard(w);
        } else if matches!(self.screen, Screen::Main) {
            self.keep_hint();
        }
        if let Some((msg, t)) = &self.toast {
            if t.elapsed() > Duration::from_secs(4) {
                self.toast = None;
            } else {
                let msg = msg.clone();
                egui::Area::new(egui::Id::unique("toast")).anchor(egui::Align2::CENTER_BOTTOM, [0.0, -24.0]).show(&ctx, |ui| {
                    egui::Frame::popup(ui.style()).show(ui, |ui| ui.label(RichText::new(msg).size(16.0)));
                });
                ctx.request_repaint_after(Duration::from_millis(250));
            }
        }
    }

    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        self.keep_hint();
    }
}

impl App {
    // ---------------------------------------------------------------------------------------
    // the wizard

    /// Returns true when finished (or cancelled).
    fn wizard_ui(&mut self, ui: &mut egui::Ui, ctx: &egui::Context, w: &mut Wizard) -> bool {
        const STEPS: [&str; 4] = ["Input", "Game picture", "Category", "Check"];
        let mut done = false;
        egui::Panel::top("steps").show(ui, |ui| {
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                ui.heading("Setup");
                ui.add_space(20.0);
                for (i, s) in STEPS.iter().enumerate() {
                    let text = RichText::new(format!("{}. {s}", i + 1)).size(15.0);
                    ui.label(if i == w.step { text.strong().color(ACCENT) } else if i < w.step { text.color(GOOD) } else { text.weak() });
                    if i + 1 < STEPS.len() {
                        ui.label(RichText::new("›").weak());
                    }
                }
            });
            ui.add_space(4.0);
        });
        let status = self.engine.shared.status.lock().unwrap().clone();
        let receiving = status.received_fps > 0.0;
        egui::Panel::bottom("nav").show(ui, |ui| {
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                if w.step > 0 && ui.button("‹ Back").clicked() {
                    w.step -= 1;
                    if w.step < 3 {
                        self.engine.send(Cmd::Detect(None));
                    }
                }
                if self.settings.profile().is_some() && ui.button("Cancel").clicked() {
                    if let Some(p) = self.settings.profile().cloned() {
                        self.engine.send(Cmd::FindFeed(false));
                        self.start_profile(&p);
                    }
                    done = true;
                }
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let (label, ok) = match w.step {
                        0 => ("Next ›", receiving),
                        1 => ("Next ›", w.crop.is_some()),
                        2 => ("Next ›", true),
                        _ => ("Finish", true),
                    };
                    let b = ui.add_enabled(ok, egui::Button::new(RichText::new(label).size(16.0).strong()).min_size(Vec2::new(110.0, 30.0)));
                    if b.clicked() {
                        match w.step {
                            0 => {
                                w.frame_size = (status.w, status.h);
                                if w.crop.is_some_and(|c| c.x1 > status.w || c.y1 > status.h) {
                                    w.crop = None;
                                    w.crop_edited = false;
                                }
                                self.engine.send(Cmd::FindFeed(true));
                                w.step = 1;
                            }
                            1 => {
                                self.engine.send(Cmd::FindFeed(false));
                                if w.name.is_empty() {
                                    w.name = w.source.as_ref().map(|s| s.label()).unwrap_or_default();
                                }
                                w.step = 2;
                            }
                            2 => {
                                self.engine.send(Cmd::Crop(w.crop));
                                self.engine.send(Cmd::NewRun);
                                self.engine.send(Cmd::Detect(Some(DetectCfg { category: w.category, language: w.language, hint: None, view: LayoutView::default() })));
                                w.seen_screens = 0;
                                w.step = 3;
                            }
                            _ => {
                                self.finish_wizard(w);
                                done = true;
                            }
                        }
                    }
                    if !ok {
                        ui.label(
                            RichText::new(match w.step {
                                0 => "waiting for frames from the input…",
                                _ => "waiting for the game picture…",
                            })
                            .weak(),
                        );
                    }
                });
            });
            ui.add_space(6.0);
        });
        egui::CentralPanel::default().show(ui, |ui| match w.step {
            0 => self.step_input(ui, ctx, w, &status),
            1 => self.step_crop(ui, ctx, w),
            2 => step_category(ui, w),
            _ => self.step_check(ui, ctx, w, &status),
        });
        done
    }

    fn step_input(&mut self, ui: &mut egui::Ui, ctx: &egui::Context, w: &mut Wizard, status: &crate::engine::Status) {
        ui.label(RichText::new("Where does the game picture come from?").size(18.0));
        ui.add_space(4.0);
        ui.label("In OBS, click Start Virtual Camera (in Controls). The OBS Virtual Camera then shows here like a webcam. A capture card works too, when OBS is not using it.");
        ui.add_space(8.0);
        let mut pick: Option<SourceSpec> = None;
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                ui.set_width(330.0);
                for c in &w.cameras {
                    let spec = SourceSpec::Camera { name: c.clone() };
                    let label = if c.to_lowercase().contains("obs virtual camera") { format!("{c}  (recommended)") } else { c.clone() };
                    if ui.radio(w.source.as_ref() == Some(&spec), label).clicked() {
                        pick = Some(spec);
                    }
                }
                if w.cameras.is_empty() {
                    ui.colored_label(WARN, "No cameras found. Start the OBS Virtual Camera, then Refresh.");
                }
                if ui.button("⟳ Refresh").clicked() {
                    w.cameras = cameras();
                }
                ui.add_space(10.0);
                let is_video = matches!(w.source, Some(SourceSpec::Video { .. }));
                if ui.radio(is_video, "A video file (to try it out; needs ffmpeg)").clicked() && !w.video_path.trim().is_empty() {
                    pick = Some(SourceSpec::Video { path: w.video_path.trim().trim_matches('"').to_string() });
                }
                ui.horizontal(|ui| {
                    let r = ui.add(egui::TextEdit::singleline(&mut w.video_path).hint_text("C:\\path\\to\\run.mp4").desired_width(240.0));
                    if (ui.button("Play").clicked() || (r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)))) && !w.video_path.trim().is_empty() {
                        pick = Some(SourceSpec::Video { path: w.video_path.trim().trim_matches('"').to_string() });
                    }
                });
            });
            ui.separator();
            ui.vertical(|ui| {
                match (&status.error, status.received_fps > 0.0) {
                    (Some(e), _) => {
                        ui.colored_label(WARN, e);
                    }
                    (None, true) => {
                        ui.colored_label(GOOD, format!("✔ {}×{}, {:.0} frames a second", status.w, status.h, status.received_fps));
                    }
                    (None, false) if w.source.is_some() => {
                        ui.label("Opening… (the OBS Virtual Camera sends nothing until it is started in OBS)");
                    }
                    _ => {}
                }
                if let Some((tex, size)) = self.preview_texture(ctx) {
                    let avail = Rect::from_min_size(ui.cursor().min, Vec2::new(ui.available_width(), (ui.available_height() - 10.0).max(100.0)));
                    let r = fit(avail, size);
                    ui.allocate_rect(avail, Sense::hover());
                    ui.painter().image(tex.id(), r, Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)), Color32::WHITE);
                }
            });
        });
        if let Some(spec) = pick {
            if w.source.as_ref() != Some(&spec) {
                self.preview = None;
                self.engine.send(Cmd::Source(Some(spec.clone())));
                w.source = Some(spec);
            }
        }
    }

    fn step_crop(&mut self, ui: &mut egui::Ui, ctx: &egui::Context, w: &mut Wizard) {
        let (samples, found) = *self.engine.shared.feed.lock().unwrap();
        if !w.crop_edited {
            if let Some(c) = found {
                w.crop = Some(c);
            }
        }
        ui.label(RichText::new("Where is the game in the picture?").size(18.0));
        ui.horizontal(|ui| {
            if w.crop_edited {
                ui.label("Drag the corners or the box to fit the game picture exactly (no borders, no timer).");
            } else if found.is_some() {
                ui.colored_label(GOOD, format!("✔ Found from what moves on screen ({samples} samples). Play for a bit and it gets more exact; drag to adjust."));
            } else {
                ui.label(format!("Play the game for a few seconds: the part that moves is the game ({samples} samples)…"));
            }
        });
        ui.horizontal(|ui| {
            if ui.button("Use the whole picture").clicked() {
                w.crop = Some(Crop::full(w.frame_size.0, w.frame_size.1));
                w.crop_edited = true;
            }
            if ui.button("Detect again").clicked() {
                w.crop_edited = false;
                w.crop = None;
                self.engine.send(Cmd::FindFeed(true));
            }
            if let Some(c) = w.crop {
                ui.label(RichText::new(format!("x {}–{}, y {}–{}  ({}×{})", c.x0, c.x1, c.y0, c.y1, c.w(), c.h())).weak());
            }
        });
        let Some((tex, size)) = self.preview_texture(ctx) else {
            ui.label("No picture from the input.");
            return;
        };
        let avail = Rect::from_min_size(ui.cursor().min, ui.available_size());
        ui.allocate_rect(avail, Sense::hover());
        let r = fit(avail, size);
        let p = ui.painter();
        p.image(tex.id(), r, Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)), Color32::WHITE);
        let Some(c) = w.crop else { return };
        let s = r.width() / size[0] as f32;
        let to_screen = |x: usize, y: usize| Pos2::new(r.min.x + x as f32 * s, r.min.y + y as f32 * s);
        let cr = Rect::from_min_max(to_screen(c.x0, c.y0), to_screen(c.x1, c.y1));
        // dim what is outside
        let dim = Color32::from_black_alpha(150);
        p.rect_filled(Rect::from_min_max(r.min, Pos2::new(r.max.x, cr.min.y)), 0.0, dim);
        p.rect_filled(Rect::from_min_max(Pos2::new(r.min.x, cr.max.y), r.max), 0.0, dim);
        p.rect_filled(Rect::from_min_max(Pos2::new(r.min.x, cr.min.y), Pos2::new(cr.min.x, cr.max.y)), 0.0, dim);
        p.rect_filled(Rect::from_min_max(Pos2::new(cr.max.x, cr.min.y), Pos2::new(r.max.x, cr.max.y)), 0.0, dim);
        p.rect_stroke(cr, 0.0, Stroke::new(2.0, ACCENT), StrokeKind::Outside);

        // handles
        let hs = 9.0;
        let mut handles = vec![(Handle::Move, cr.shrink(hs))];
        for (right, bottom) in [(false, false), (true, false), (false, true), (true, true)] {
            let pt = Pos2::new(if right { cr.max.x } else { cr.min.x }, if bottom { cr.max.y } else { cr.min.y });
            handles.push((Handle::Corner(right, bottom), Rect::from_center_size(pt, Vec2::splat(hs * 2.0))));
        }
        for (h, hr) in handles.iter().rev() {
            if let Handle::Corner(..) = h {
                p.rect_filled(hr.shrink(3.0), 2.0, ACCENT);
            }
            let resp = ui.interact(*hr, ui.scope_id().with(("crop", format!("{:?}", hr.min))), Sense::drag());
            if resp.drag_started() {
                w.drag = Some(*h);
            }
            if resp.hovered() || resp.dragged() {
                ctx.set_cursor_icon(match h {
                    Handle::Move => egui::CursorIcon::Move,
                    Handle::Corner(r, b) if r == b => egui::CursorIcon::ResizeNwSe,
                    _ => egui::CursorIcon::ResizeNeSw,
                });
            }
        }
        if let Some(h) = w.drag {
            let d = ui.input(|i| i.pointer.delta());
            if ui.input(|i| i.pointer.primary_down()) {
                if d != Vec2::ZERO {
                    let dx = (d.x / s).round() as i64;
                    let dy = (d.y / s).round() as i64;
                    let mv = |v: usize, by: i64| (v as i64 + by).max(0) as usize;
                    let mut c = c;
                    match h {
                        Handle::Move => {
                            let dx = dx.clamp(-(c.x0 as i64), (size[0] - c.x1) as i64);
                            let dy = dy.clamp(-(c.y0 as i64), (size[1] - c.y1) as i64);
                            c = Crop { x0: mv(c.x0, dx), x1: mv(c.x1, dx), y0: mv(c.y0, dy), y1: mv(c.y1, dy) };
                        }
                        Handle::Corner(right, bottom) => {
                            if right {
                                c.x1 = mv(c.x1, dx).min(size[0]).max(c.x0 + 32);
                            } else {
                                c.x0 = mv(c.x0, dx).min(c.x1 - 32);
                            }
                            if bottom {
                                c.y1 = mv(c.y1, dy).min(size[1]).max(c.y0 + 32);
                            } else {
                                c.y0 = mv(c.y0, dy).min(c.y1 - 32);
                            }
                        }
                    }
                    w.crop = Some(c);
                    w.crop_edited = true;
                }
            } else {
                w.drag = None;
            }
        }
    }

    fn step_check(&mut self, ui: &mut egui::Ui, ctx: &egui::Context, w: &mut Wizard, status: &crate::engine::Status) {
        ui.label(RichText::new("Enter any cave").size(18.0));
        ui.label("Go into a cave (or load a save in front of one). When the cave's name falls in, the seed and layout show here. You can also finish now and check later.");
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            let (txt, col) = if status.on_entry_screen {
                ("● cave name on screen, reading…", ACCENT)
            } else if status.screens > 0 {
                ("✔ saw a cave name screen", GOOD)
            } else {
                ("waiting for a cave name screen…", Color32::GRAY)
            };
            ui.colored_label(col, RichText::new(txt).size(16.0));
            if status.received_fps == 0.0 {
                ui.colored_label(WARN, "no frames from the input");
            }
        });
        w.seen_screens = status.screens;
        ui.add_space(6.0);
        ui.columns(2, |cols| {
            cols[0].label(RichText::new("What the detector sees").weak());
            if let (Some((tex, size)), Some(c)) = (self.preview_texture(ctx), w.crop) {
                let avail = Rect::from_min_size(cols[0].cursor().min, Vec2::new(cols[0].available_width(), cols[0].available_width() * 0.75));
                cols[0].allocate_rect(avail, Sense::hover());
                let uv = Rect::from_min_max(
                    Pos2::new(c.x0 as f32 / size[0] as f32, c.y0 as f32 / size[1] as f32),
                    Pos2::new(c.x1 as f32 / size[0] as f32, c.y1 as f32 / size[1] as f32),
                );
                cols[0].painter().image(tex.id(), fit(avail, [c.w(), c.h()]), uv, Color32::WHITE);
            }
            if let Some(e) = self.engine.shared.current() {
                self.entry_header(&mut cols[1], &e);
                if let Some((tex, size)) = self.layout_texture(ctx, &e) {
                    let avail = Rect::from_min_size(cols[1].cursor().min, cols[1].available_size());
                    cols[1].allocate_rect(avail, Sense::hover());
                    cols[1].painter().image(tex.id(), fit(avail, size), Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)), Color32::WHITE);
                }
            }
        });
    }

    fn finish_wizard(&mut self, w: &Wizard) {
        let (Some(source), Some(crop)) = (w.source.clone(), w.crop) else { return };
        let hint = *self.engine.shared.hint.lock().unwrap();
        let old = w.editing.and_then(|i| self.settings.profiles.get(i));
        let p = Profile {
            name: if w.name.trim().is_empty() { source.label() } else { w.name.trim().to_string() },
            source,
            crop,
            frame_size: w.frame_size,
            category: w.category,
            language: w.language,
            // a new crop or input changes the scale of the name
            hint: hint.or(old.filter(|o| o.crop == crop && o.frame_size == w.frame_size).and_then(|o| o.hint)),
            view: old.map(|o| o.view.clone()).unwrap_or_default(),
        };
        let i = match w.editing {
            Some(i) if i < self.settings.profiles.len() => {
                self.settings.profiles[i] = p.clone();
                i
            }
            _ => {
                self.settings.profiles.push(p.clone());
                self.settings.profiles.len() - 1
            }
        };
        self.settings.active = Some(i);
        self.save();
        self.engine.send(Cmd::FindFeed(false));
        // keep the run going (the check may already have found a seed)
        self.engine.send(Cmd::Detect(Some(detect_cfg(&p))));
        self.saved_hint = p.hint;
        self.toast(format!("Saved profile \"{}\"", p.name));
    }

    // ---------------------------------------------------------------------------------------
    // the main view

    fn entry_header(&self, ui: &mut egui::Ui, e: &Entry) {
        ui.horizontal_wrapped(|ui| {
            ui.label(RichText::new(e.title()).size(24.0).strong());
            let sure = e.confidence == "high" || e.chained;
            ui.label(RichText::new(e.seed_text()).monospace().size(20.0).color(if sure { GOOD } else { WARN }));
            ui.label(RichText::new(format!("{}{}", e.confidence, if e.chained { ", chained" } else { "" })).weak());
            if let Some(s) = e.score {
                ui.label(RichText::new(format!("judge {s:.0}")).weak());
            }
            if let Some(err) = &e.render_error {
                ui.colored_label(WARN, err);
            }
        });
    }

    fn main_ui(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        let status = self.engine.shared.status.lock().unwrap().clone();
        let profile = self.settings.profile().cloned();
        egui::Panel::top("bar").show(ui, |ui| {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                let names: Vec<String> = self.settings.profiles.iter().map(|p| p.name.clone()).collect();
                let mut active = self.settings.active.unwrap_or(0);
                egui::ComboBox::from_id_salt("profile")
                    .selected_text(names.get(active).cloned().unwrap_or_else(|| "no profile".into()))
                    .show_ui(ui, |ui| {
                        for (i, n) in names.iter().enumerate() {
                            ui.selectable_value(&mut active, i, n);
                        }
                    });
                if Some(active) != self.settings.active && active < self.settings.profiles.len() {
                    self.keep_hint();
                    self.settings.active = Some(active);
                    self.save();
                    let p = self.settings.profiles[active].clone();
                    self.engine.send(Cmd::NewRun);
                    self.start_profile(&p);
                }
                if ui.button("Setup…").on_hover_text("Change the input, the game picture or the category").clicked() {
                    self.keep_hint();
                    self.screen = Screen::Wizard(self.new_wizard(self.settings.active));
                }
                if ui.button("New profile…").clicked() {
                    self.keep_hint();
                    self.screen = Screen::Wizard(self.new_wizard(None));
                }
                ui.separator();
                if ui.button("New run").on_hover_text("Clear the sublevels so far (the next seed is not linked to the last one)").clicked() {
                    self.engine.send(Cmd::NewRun);
                    self.selected = None;
                }
                if ui.button("📋 Copy Browser Source URL").on_hover_text(format!("{}\nIn OBS: Sources › + › Browser, paste it as the URL", self.overlay.url())).clicked() {
                    ctx.copy_text(self.overlay.url());
                    self.toast(format!("Copied {}", self.overlay.url()));
                }
            });
            ui.horizontal(|ui| {
                let input = status.source.clone().unwrap_or_else(|| "no input".into());
                if let Some(e) = &status.error {
                    ui.colored_label(WARN, format!("{input}: {e}"));
                } else if status.received_fps > 0.0 {
                    ui.colored_label(GOOD, format!("● {input}  {}×{}  {:.0} fps", status.w, status.h, status.received_fps));
                } else {
                    ui.colored_label(WARN, format!("● {input}: no frames (is the virtual camera started?)"));
                }
                if let Some(p) = &profile {
                    if status.w > 0 && (status.w, status.h) != p.frame_size {
                        ui.colored_label(WARN, format!("the input is {}×{} but was {}×{} at setup: run Setup again", status.w, status.h, p.frame_size.0, p.frame_size.1));
                    }
                    ui.label(RichText::new(format!("{} · {}", p.category.label(), if p.language == Language::Auto { "any language".into() } else { p.language.label().to_string() })).weak());
                }
                if status.on_entry_screen {
                    ui.colored_label(ACCENT, "● reading the cave name…");
                }
                if let Some(err) = &self.overlay.error {
                    ui.colored_label(WARN, format!("Browser Source off: {err}"));
                }
                if let Err(e) = &*self.engine.shared.cavegen.lock().unwrap() {
                    ui.colored_label(WARN, e);
                }
            });
            ui.add_space(4.0);
        });

        let entries = self.engine.shared.entries.lock().unwrap().clone();
        egui::Panel::right("run").resizable(true).default_size(270.0).show(ui, |ui| {
            ui.add_space(4.0);
            ui.label(RichText::new("This run").strong());
            egui::ScrollArea::vertical().max_height(ui.available_height() * 0.55).stick_to_bottom(true).show(ui, |ui| {
                if entries.is_empty() {
                    ui.label(RichText::new("Sublevels show here as you enter them.").weak());
                }
                for e in &entries {
                    let sure = e.confidence == "high" || e.chained;
                    let text = format!("{:<24} {}", e.title(), e.seed_text());
                    let col = if e.layout_seed.is_none() { Color32::GRAY } else if sure { Color32::LIGHT_GRAY } else { WARN };
                    let picked = self.selected == Some(e.key);
                    if ui.selectable_label(picked, RichText::new(text).monospace().color(col)).clicked() {
                        self.selected = if picked { None } else { Some(e.key) };
                    }
                }
            });
            ui.separator();
            if let Some(i) = self.settings.active {
                let mut view = self.settings.profiles[i].view.clone();
                ui.checkbox(&mut view.quick_glance, "QuickGlance (discs behind what matters)");
                ui.checkbox(&mut view.pretty, "Pretty (floor pictures)");
                if view != self.settings.profiles[i].view {
                    self.settings.profiles[i].view = view.clone();
                    self.save();
                    self.engine.send(Cmd::View(view));
                }
            }
            ui.separator();
            egui::CollapsingHeader::new("Input").default_open(true).show(ui, |ui| {
                if let (Some((tex, size)), Some(p)) = (self.preview_texture(ctx), &profile) {
                    let c = p.crop;
                    let wdt = ui.available_width();
                    let avail = Rect::from_min_size(ui.cursor().min, Vec2::new(wdt, wdt * c.h() as f32 / c.w().max(1) as f32));
                    ui.allocate_rect(avail, Sense::hover());
                    let uv = Rect::from_min_max(
                        Pos2::new(c.x0 as f32 / size[0] as f32, c.y0 as f32 / size[1] as f32),
                        Pos2::new(c.x1 as f32 / size[0] as f32, c.y1 as f32 / size[1] as f32),
                    );
                    ui.painter().image(tex.id(), avail, uv, Color32::WHITE);
                }
            });
            ui.checkbox(&mut self.show_log, "Show the log");
        });

        if self.show_log {
            egui::Panel::bottom("log").resizable(true).default_size(150.0).show(ui, |ui| {
                egui::ScrollArea::vertical().stick_to_bottom(true).show(ui, |ui| {
                    for l in self.engine.shared.log.lock().unwrap().iter() {
                        ui.label(RichText::new(l).monospace().size(12.0));
                    }
                });
            });
        }

        egui::CentralPanel::default().show(ui, |ui| {
            let shown = match self.selected {
                Some(k) => entries.iter().find(|e| e.key == k).cloned(),
                None => entries.iter().rev().find(|e| e.layout_seed.is_some()).cloned(),
            };
            match shown {
                None => {
                    ui.vertical_centered(|ui| {
                        ui.add_space(ui.available_height() * 0.35);
                        ui.label(RichText::new("Enter a cave: its layout shows here.").size(20.0).weak());
                        ui.label(RichText::new(format!("Browser Source for OBS: {}", self.overlay.url())).weak());
                    });
                }
                Some(e) => {
                    self.entry_header(ui, &e);
                    match self.layout_texture(ctx, &e) {
                        Some((tex, size)) => {
                            let avail = Rect::from_min_size(ui.cursor().min, ui.available_size());
                            ui.allocate_rect(avail, Sense::hover());
                            ui.painter().image(tex.id(), fit(avail, size), Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)), Color32::WHITE);
                        }
                        None if e.layout_seed.is_some() && e.render_error.is_none() => {
                            ui.label("drawing…");
                        }
                        None => {}
                    }
                }
            }
        });
    }
}

fn step_category(ui: &mut egui::Ui, w: &mut Wizard) {
    ui.label(RichText::new("What are you running?").size(18.0));
    ui.add_space(6.0);
    for c in Category::ALL {
        ui.radio_value(&mut w.category, c, RichText::new(c.label()).size(16.0));
    }
    ui.label(RichText::new("Challenge mode (attk, key, cmat, 700k) is not in this version yet.").weak());
    ui.add_space(12.0);
    ui.label(RichText::new("Game language").size(16.0));
    for l in Language::ALL {
        ui.radio_value(&mut w.language, l, l.label());
    }
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        ui.label("Profile name");
        ui.text_edit_singleline(&mut w.name);
    });
}

pub fn run() -> eframe::Result {
    let opts = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_title("Pikmin 2 live layouts").with_inner_size([1100.0, 720.0]).with_min_inner_size([760.0, 480.0]),
        ..Default::default()
    };
    eframe::run_native("p2live", opts, Box::new(|cc| Ok(Box::new(App::new(cc)))))
}

#[allow(dead_code)]
fn _assert_send() {
    fn is_send<T: Send>() {}
    is_send::<Arc<crate::engine::Shared>>();
}
