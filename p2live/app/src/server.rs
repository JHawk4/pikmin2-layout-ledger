//! The OBS Browser Source: a page on this computer only (127.0.0.1) that shows the newest
//! layout. The page polls `/state`; a new picture is at `/layout.png?v=<version>`.
//!
//!   /           the overlay (transparent background; `?caption=0` hides the text line,
//!               `?size=N` sets the text size in pixels)
//!   /state      JSON: the current sublevel, seed, confidence and picture version
//!   /layout.png the current layout picture

use std::sync::Arc;
use std::thread::JoinHandle;

use serde_json::json;
use tiny_http::{Header, Response, Server};

use crate::engine::Shared;

const PAGE: &str = include_str!("overlay.html");

pub struct Overlay {
    pub port: u16,
    pub error: Option<String>,
    _thread: Option<JoinHandle<()>>,
}

impl Overlay {
    pub fn url(&self) -> String {
        format!("http://127.0.0.1:{}/", self.port)
    }
}

fn header(k: &str, v: &str) -> Header {
    Header::from_bytes(k.as_bytes(), v.as_bytes()).unwrap()
}

pub fn start(shared: Arc<Shared>, port: u16) -> Overlay {
    let server = match Server::http(("127.0.0.1", port)) {
        Ok(s) => s,
        Err(e) => return Overlay { port, error: Some(format!("port {port} is in use or blocked ({e})")), _thread: None },
    };
    let t = std::thread::Builder::new()
        .name("overlay".into())
        .spawn(move || {
            for req in server.incoming_requests() {
                let path = req.url().split('?').next().unwrap_or("/").to_string();
                let nocache = header("Cache-Control", "no-store");
                let res = match path.as_str() {
                    "/" | "/index.html" => req.respond(Response::from_string(PAGE).with_header(header("Content-Type", "text/html; charset=utf-8")).with_header(nocache)),
                    "/state" => {
                        let cur = shared.current();
                        let body = match &cur {
                            Some(e) => json!({
                                "version": e.version as u64 * 1_000_000 + e.key as u64,
                                "title": e.title(),
                                "cave": e.cave,
                                "sublevel": e.sublevel,
                                "seed": e.seed_text(),
                                "confidence": e.confidence,
                                "chained": e.chained,
                                "score": e.score,
                                "picture": e.png.is_some(),
                            }),
                            None => json!({ "version": 0, "picture": false }),
                        };
                        req.respond(Response::from_string(body.to_string()).with_header(header("Content-Type", "application/json")).with_header(nocache))
                    }
                    "/layout.png" => match shared.current().and_then(|e| e.png) {
                        Some(png) => req.respond(Response::from_data(png.as_ref().clone()).with_header(header("Content-Type", "image/png")).with_header(nocache)),
                        None => req.respond(Response::from_string("no layout yet").with_status_code(404)),
                    },
                    _ => req.respond(Response::from_string("not found").with_status_code(404)),
                };
                let _ = res;
            }
        })
        .ok();
    Overlay { port, error: None, _thread: t }
}
