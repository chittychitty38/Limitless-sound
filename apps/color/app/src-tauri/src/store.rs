//! Keeps the profile and the on/off switch between launches.

use color_core::Profile;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
struct Saved {
    filter_on: bool,
    profile: Option<serde_json::Value>,
}

fn path(app: &AppHandle) -> Option<std::path::PathBuf> {
    app.path().app_config_dir().ok().map(|d| d.join("profile.json"))
}

pub fn load(app: &AppHandle) -> (Profile, bool) {
    let Some(p) = path(app) else { return (Profile::default(), false) };
    let Ok(text) = std::fs::read_to_string(p) else { return (Profile::default(), false) };
    let saved: Saved = serde_json::from_str(&text).unwrap_or_default();
    let profile = saved.profile.and_then(|v| Profile::from_json(&v.to_string()).ok()).unwrap_or_default();
    (profile, saved.filter_on)
}

pub fn save(app: &AppHandle, profile: &Profile, filter_on: bool) {
    let Some(p) = path(app) else { return };
    if let Some(dir) = p.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let saved = Saved { filter_on, profile: serde_json::to_value(profile).ok() };
    let tmp = p.with_extension("json.tmp");
    if std::fs::write(&tmp, serde_json::to_string_pretty(&saved).unwrap_or_default()).is_ok() {
        let _ = std::fs::rename(tmp, p);
    }
}
