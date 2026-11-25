//! Saved settings: named profiles (input, crop, category, language) and the overlay port. Kept
//! next to the exe (`p2live-settings.json`) so a copied folder brings its setup along, or in
//! %APPDATA%\p2live when that folder is not writable.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use crate::capture::{Crop, SourceSpec};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Category {
    /// Pay Off Debt: the nine caves of the debt route, pod judge.
    Pod,
    /// All Treasures: every story cave, AT judge.
    At,
}

impl Category {
    pub const ALL: [Category; 2] = [Category::Pod, Category::At];
    pub fn label(self) -> &'static str {
        match self {
            Category::Pod => "Pay Off Debt",
            Category::At => "All Treasures",
        }
    }
    pub fn judge(self) -> &'static str {
        match self {
            Category::Pod => "pod",
            Category::At => "at",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Language {
    /// Recognize English and Japanese names.
    Auto,
    En,
    Ja,
}

impl Language {
    pub const ALL: [Language; 3] = [Language::Auto, Language::En, Language::Ja];
    pub fn label(self) -> &'static str {
        match self {
            Language::Auto => "Detect automatically",
            Language::En => "English (USA / Europe)",
            Language::Ja => "Japanese",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LayoutView {
    /// CaveGen's QuickGlance discs behind what matters (pod, treasures, exit, ...).
    pub quick_glance: bool,
    /// Draw the vanilla map units as pictures of the real floor.
    pub pretty: bool,
}

impl Default for LayoutView {
    fn default() -> Self {
        LayoutView { quick_glance: true, pretty: false }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Profile {
    pub name: String,
    pub source: SourceSpec,
    /// The game picture inside the capture, for a capture of `frame_size`.
    pub crop: Crop,
    pub frame_size: (usize, usize),
    pub category: Category,
    pub language: Language,
    /// The name's scale learned on earlier screens (sy, sx/sy): later screens read faster.
    #[serde(default)]
    pub hint: Option<(f64, f64)>,
    #[serde(default)]
    pub view: LayoutView,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Settings {
    pub profiles: Vec<Profile>,
    /// The profile used at start.
    pub active: Option<usize>,
    /// Port of the Browser Source page on this computer.
    pub port: u16,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { profiles: Vec::new(), active: None, port: 8787 }
    }
}

fn exe_dir_file() -> Option<PathBuf> {
    Some(std::env::current_exe().ok()?.parent()?.join("p2live-settings.json"))
}

fn appdata_file() -> Option<PathBuf> {
    Some(PathBuf::from(std::env::var_os("APPDATA")?).join("p2live").join("settings.json"))
}

impl Settings {
    pub fn load() -> Settings {
        for p in [exe_dir_file(), appdata_file()].into_iter().flatten() {
            if let Ok(text) = std::fs::read_to_string(&p) {
                if let Ok(s) = serde_json::from_str(&text) {
                    return s;
                }
            }
        }
        Settings::default()
    }

    /// Save next to the exe, else in %APPDATA%. Returns where it went.
    pub fn save(&self) -> Result<PathBuf, String> {
        let text = serde_json::to_string_pretty(self).map_err(|e| e.to_string())?;
        let mut last = String::from("no place to save settings");
        for p in [exe_dir_file(), appdata_file()].into_iter().flatten() {
            if let Some(d) = p.parent() {
                let _ = std::fs::create_dir_all(d);
            }
            match std::fs::write(&p, &text) {
                Ok(()) => return Ok(p),
                Err(e) => last = format!("{}: {e}", p.display()),
            }
        }
        Err(last)
    }

    pub fn profile(&self) -> Option<&Profile> {
        self.active.and_then(|i| self.profiles.get(i))
    }
}
