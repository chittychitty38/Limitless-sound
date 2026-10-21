//! Keeps the profile, the on/off switch and first-launch progress between launches.

use color_core::Profile;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
struct Saved {
    filter_on: bool,
    profile: Option<serde_json::Value>,
    /// The first-launch step the person reached, or "done".
    onboarding: String,
}

pub struct Loaded {
    pub profile: Profile,
    pub filter_on: bool,
    pub onboarding: String,
}

fn path(app: &AppHandle) -> Option<std::path::PathBuf> {
    app.path().app_config_dir().ok().map(|d| d.join("profile.json"))
}

pub fn load(app: &AppHandle) -> Loaded {
    let saved: Saved = path(app)
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default();
    let profile = saved.profile.and_then(|v| Profile::from_json(&v.to_string()).ok()).unwrap_or_default();
    Loaded { profile, filter_on: saved.filter_on, onboarding: saved.onboarding }
}

pub fn save(app: &AppHandle, profile: &Profile, filter_on: bool, onboarding: &str) {
    let Some(p) = path(app) else { return };
    if let Some(dir) = p.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let saved = Saved { filter_on, profile: serde_json::to_value(profile).ok(), onboarding: onboarding.to_string() };
    let tmp = p.with_extension("json.tmp");
    if std::fs::write(&tmp, serde_json::to_string_pretty(&saved).unwrap_or_default()).is_ok() {
        let _ = std::fs::rename(tmp, p);
    }
}
