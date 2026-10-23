//! The musician's shared settings from the Limitless Sound hub that the tuner
//! window honors: text size, high contrast, reduced motion and the language. They
//! change the window around the colors, never the swatches, the preview or the screen filter.

use serde::Serialize;
use serde_json::{json, Value};

use crate::lang::Lang;

/// How the tuner window looks and moves, and the language it speaks.
#[derive(Serialize, Clone, Copy, Debug, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct WindowPrefs {
    /// 1.0 to 2.0
    pub text_scale: f64,
    pub high_contrast: bool,
    pub reduce_motion: bool,
    /// The window's, the menus' and the assistant's language.
    pub language: Lang,
}

/// The window as it looks without the hub.
impl Default for WindowPrefs {
    fn default() -> Self {
        Self { text_scale: 1.0, high_contrast: false, reduce_motion: false, language: Lang::En }
    }
}

impl WindowPrefs {
    /// Reads the hub's `prefs`. Anything missing or unreadable stays as it is without the hub.
    pub fn from_prefs(prefs: &Value) -> Self {
        let d = Self::default();
        let flag = |key: &str, default: bool| prefs.get(key).and_then(Value::as_bool).unwrap_or(default);
        Self {
            text_scale: prefs
                .get("textScale")
                .and_then(Value::as_f64)
                .filter(|v| v.is_finite())
                .map_or(d.text_scale, |v| v.clamp(1.0, 2.0)),
            high_contrast: flag("highContrast", d.high_contrast),
            reduce_motion: flag("reduceMotion", d.reduce_motion),
            language: Self::suite_language(prefs).unwrap_or(d.language),
        }
    }

    /// The language the hub's `prefs` choose, if they choose one. One Color doesn't have
    /// means English, as in every app of the suite.
    pub fn suite_language(prefs: &Value) -> Option<Lang> {
        let value = prefs.get("language")?.as_str()?;
        Some(Lang::from_tag(value).unwrap_or_default())
    }

    /// The more accessible of two: the larger text, and each switch on if either is on.
    /// The language is the first one's.
    pub fn more_accessible(self, other: Self) -> Self {
        Self {
            text_scale: self.text_scale.max(other.text_scale),
            high_contrast: self.high_contrast || other.high_contrast,
            reduce_motion: self.reduce_motion || other.reduce_motion,
            language: self.language,
        }
    }

    /// The `prefs.applied` state for the hub: only the settings this app honors, as in use.
    /// With the language, the hub reads what Color says with a voice for it.
    pub fn applied(&self) -> Value {
        json!({"textScale": self.text_scale, "highContrast": self.high_contrast, "reduceMotion": self.reduce_motion,
               "language": self.language})
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_the_hubs_prefs() {
        let hub = json!({"speak": true, "oneVoice": true, "textScale": 1.5, "highContrast": true,
                         "reduceMotion": false, "dwellMs": 800, "scanMs": 1200, "language": "es"});
        let p = WindowPrefs::from_prefs(&hub);
        assert_eq!(p, WindowPrefs { text_scale: 1.5, high_contrast: true, reduce_motion: false, language: Lang::Es });
    }

    #[test]
    fn the_suites_language_when_it_has_one() {
        assert_eq!(WindowPrefs::suite_language(&json!({"language": "es"})), Some(Lang::Es));
        assert_eq!(WindowPrefs::suite_language(&json!({"language": "es-MX"})), Some(Lang::Es));
        assert_eq!(WindowPrefs::suite_language(&json!({"language": "en"})), Some(Lang::En));
        // A language Color doesn't have: English, like the rest of the suite.
        assert_eq!(WindowPrefs::suite_language(&json!({"language": "fr"})), Some(Lang::En));
        // An older hub that doesn't send one: the computer's language stays.
        assert_eq!(WindowPrefs::suite_language(&json!({"textScale": 1.5})), None);
        assert_eq!(WindowPrefs::suite_language(&json!({"language": 5})), None);
    }

    #[test]
    fn missing_or_odd_prefs_keep_todays_window() {
        assert_eq!(WindowPrefs::from_prefs(&json!({})), WindowPrefs::default());
        assert_eq!(WindowPrefs::from_prefs(&Value::Null), WindowPrefs::default());
        let odd = WindowPrefs::from_prefs(&json!({"textScale": "big", "highContrast": 1, "reduceMotion": null}));
        assert_eq!(odd, WindowPrefs::default());
        assert_eq!(WindowPrefs::from_prefs(&json!({"textScale": 9})).text_scale, 2.0);
        assert_eq!(WindowPrefs::from_prefs(&json!({"textScale": 0.5})).text_scale, 1.0);
        assert_eq!(WindowPrefs::from_prefs(&json!({"textScale": 1})).text_scale, 1.0);
    }

    #[test]
    fn combining_keeps_the_more_accessible_of_each() {
        let suite = WindowPrefs { text_scale: 1.25, high_contrast: true, reduce_motion: false, language: Lang::Es };
        let system = WindowPrefs { reduce_motion: true, ..WindowPrefs::default() };
        let both = WindowPrefs { text_scale: 1.25, high_contrast: true, reduce_motion: true, language: Lang::Es };
        assert_eq!(suite.more_accessible(system), both);
        assert_eq!(system.more_accessible(suite), WindowPrefs { language: Lang::En, ..both });
        let bigger = WindowPrefs { text_scale: 1.75, ..WindowPrefs::default() };
        assert_eq!(suite.more_accessible(bigger).text_scale, 1.75);
        // Without the hub, nothing changes.
        assert_eq!(WindowPrefs::default().more_accessible(WindowPrefs::default()), WindowPrefs::default());
    }

    #[test]
    fn applied_reports_only_what_the_window_honors() {
        // Exactly these four: never dwellMs, scanMs, speak or oneVoice.
        let p = WindowPrefs { text_scale: 1.5, high_contrast: true, reduce_motion: false, language: Lang::Es };
        assert_eq!(p.applied(), json!({"textScale": 1.5, "highContrast": true, "reduceMotion": false, "language": "es"}));
    }

    #[test]
    fn the_window_gets_the_same_names() {
        let p = WindowPrefs { text_scale: 2.0, high_contrast: false, reduce_motion: true, language: Lang::En };
        assert_eq!(serde_json::to_value(p).unwrap(), p.applied());
    }
}
