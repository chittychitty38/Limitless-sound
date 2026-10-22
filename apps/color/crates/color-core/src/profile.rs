//! A person's color profile: the fader settings plus pinned colors, and the
//! transform they produce. The same math runs in the tuner preview (JavaScript)
//! and on the whole screen (this crate), so keep the two in step.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::color::*;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Settings {
    #[serde(rename = "type")]
    pub cvd: CvdType,
    pub severity: f64,
    pub daltonize: f64,
    pub rg_split: f64,
    pub by_split: f64,
    pub red_shift: f64,
    pub green_shift: f64,
    pub yellow_shift: f64,
    pub blue_shift: f64,
    pub saturation: f64,
    pub contrast: f64,
    pub focus: f64,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            cvd: CvdType::Deutan,
            severity: 0.8,
            daltonize: 0.0,
            rg_split: 0.0,
            by_split: 0.0,
            red_shift: 0.0,
            green_shift: 0.0,
            yellow_shift: 0.0,
            blue_shift: 0.0,
            saturation: 1.0,
            contrast: 1.0,
            focus: 0.08,
        }
    }
}

/// Every numeric setting with its allowed range. Names match the JSON keys.
pub const RANGES: [(&str, f64, f64); 11] = [
    ("severity", 0.0, 1.0),
    ("daltonize", 0.0, 1.0),
    ("rgSplit", -1.0, 1.0),
    ("bySplit", -1.0, 1.0),
    ("redShift", -60.0, 60.0),
    ("greenShift", -60.0, 60.0),
    ("yellowShift", -60.0, 60.0),
    ("blueShift", -60.0, 60.0),
    ("saturation", 0.5, 2.0),
    ("contrast", 0.7, 1.5),
    ("focus", 0.03, 0.18),
];

impl Settings {
    pub fn get(&self, key: &str) -> Option<f64> {
        Some(match key {
            "severity" => self.severity,
            "daltonize" => self.daltonize,
            "rgSplit" => self.rg_split,
            "bySplit" => self.by_split,
            "redShift" => self.red_shift,
            "greenShift" => self.green_shift,
            "yellowShift" => self.yellow_shift,
            "blueShift" => self.blue_shift,
            "saturation" => self.saturation,
            "contrast" => self.contrast,
            "focus" => self.focus,
            _ => return None,
        })
    }

    /// Sets a numeric setting, clamped to its range. Returns false for unknown keys.
    pub fn set(&mut self, key: &str, v: f64) -> bool {
        if !v.is_finite() {
            return false;
        }
        let Some(&(_, lo, hi)) = RANGES.iter().find(|r| r.0 == key) else { return false };
        let v = v.clamp(lo, hi);
        match key {
            "severity" => self.severity = v,
            "daltonize" => self.daltonize = v,
            "rgSplit" => self.rg_split = v,
            "bySplit" => self.by_split = v,
            "redShift" => self.red_shift = v,
            "greenShift" => self.green_shift = v,
            "yellowShift" => self.yellow_shift = v,
            "blueShift" => self.blue_shift = v,
            "saturation" => self.saturation = v,
            "contrast" => self.contrast = v,
            "focus" => self.focus = v,
            _ => return false,
        }
        true
    }

    /// Clamps every value into range (for profiles loaded from disk).
    pub fn clamped(mut self) -> Self {
        for (k, _, _) in RANGES {
            let v = self.get(k).unwrap_or(0.0);
            self.set(k, v);
        }
        self
    }
}

/// A pinned color: anything near `from` on screen is shown as `to`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Anchor {
    pub from: String,
    pub to: String,
    #[serde(default)]
    pub label: String,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Profile {
    #[serde(rename = "S", alias = "settings")]
    pub settings: Settings,
    #[serde(default)]
    pub anchors: BTreeMap<String, Anchor>,
}

impl Profile {
    pub fn from_json(s: &str) -> Result<Profile, serde_json::Error> {
        let mut p: Profile = serde_json::from_str(s)?;
        p.settings = p.settings.clamped();
        p.anchors.retain(|_, a| hex_to_srgb(&a.from).is_some() && hex_to_srgb(&a.to).is_some());
        Ok(p)
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(self).expect("profile serializes")
    }

    /// True when the profile leaves every color as it is.
    pub fn is_identity(&self) -> bool {
        let d = Settings::default();
        let s = &self.settings;
        self.anchors.is_empty()
            && s.daltonize == 0.0
            && s.rg_split == 0.0
            && s.by_split == 0.0
            && s.red_shift == 0.0
            && s.green_shift == 0.0
            && s.yellow_shift == 0.0
            && s.blue_shift == 0.0
            && s.saturation == d.saturation
            && s.contrast == d.contrast
    }

    pub fn transform(&self) -> Transform {
        Transform::new(self)
    }
}

/// Hue bands (OKLCH degrees) the "Move reds/yellows/greens/blues" faders act on.
const BANDS: [(&str, f64); 4] = [("redShift", 29.0), ("yellowShift", 105.0), ("greenShift", 142.0), ("blueShift", 264.0)];

fn ang_diff(a: f64, b: f64) -> f64 {
    let mut d = (a - b) % 360.0;
    if d > 180.0 {
        d -= 360.0;
    }
    if d < -180.0 {
        d += 360.0;
    }
    d
}

struct PreparedAnchor {
    origin: Rgb,
    delta: Rgb,
}

/// A ready-to-run color transform, linear sRGB in and out.
pub struct Transform {
    s: Settings,
    sim: Mat3,
    anchors: Vec<PreparedAnchor>,
    two_sigma2: f64,
}

impl Transform {
    pub fn new(p: &Profile) -> Transform {
        let s = p.settings.clone();
        let mut t = Transform { sim: s.cvd.sim_matrix(s.severity), anchors: vec![], two_sigma2: 2.0 * s.focus * s.focus, s };
        let prepared = p
            .anchors
            .values()
            .filter_map(|a| {
                let from = hex_to_lin(&a.from)?;
                let to = lin_to_oklab(hex_to_lin(&a.to)?);
                let g = t.global_lab(from);
                Some(PreparedAnchor { origin: lin_to_oklab(from), delta: [to[0] - g[0], to[1] - g[1], to[2] - g[2]] })
            })
            .collect();
        t.anchors = prepared;
        t
    }

    fn global_lab(&self, lin: Rgb) -> Rgb {
        let s = &self.s;
        let mut c = lin;
        if s.daltonize > 0.0 {
            let sm = mul(&self.sim, c);
            let e = [c[0] - sm[0], c[1] - sm[1], c[2] - sm[2]];
            let corr = if s.cvd == CvdType::Tritan {
                [e[0] + 0.7 * e[2], e[1] + 0.7 * e[2], 0.0]
            } else {
                [0.0, 0.7 * e[0] + e[1], 0.7 * e[0] + e[2]]
            };
            c = [0, 1, 2].map(|i| clamp01(c[i] + s.daltonize * corr[i]));
        }
        let [mut l, a, b] = lin_to_oklab(c);
        let mut chroma = (a * a + b * b).sqrt();
        let mut h = b.atan2(a).to_degrees();
        l += s.rg_split * a * 1.3 + s.by_split * b * 1.3;
        let cf = (chroma / 0.05).min(1.0);
        let dh: f64 = BANDS
            .iter()
            .map(|&(k, center)| {
                let d = ang_diff(h, center) / 28.0;
                s.get(k).unwrap_or(0.0) * (-d * d).exp()
            })
            .sum();
        h += dh * cf;
        chroma *= s.saturation;
        l = 0.5 + (l - 0.5) * s.contrast;
        let hr = h.to_radians();
        [l, chroma * hr.cos(), chroma * hr.sin()]
    }

    /// Applies the profile to one linear sRGB color.
    pub fn apply(&self, lin: Rgb) -> Rgb {
        let mut lab = self.global_lab(lin);
        if !self.anchors.is_empty() {
            let o = lin_to_oklab(lin);
            for a in &self.anchors {
                let dd = (o[0] - a.origin[0]).powi(2) + (o[1] - a.origin[1]).powi(2) + (o[2] - a.origin[2]).powi(2);
                let w = (-dd / self.two_sigma2).exp();
                if w > 1e-3 {
                    for i in 0..3 {
                        lab[i] += w * a.delta[i];
                    }
                }
            }
        }
        oklab_to_lin(lab).map(clamp01)
    }

    /// Applies the profile to an sRGB-encoded color (what screens and LUTs use).
    pub fn apply_srgb(&self, srgb: Rgb) -> Rgb {
        lin_to_srgb3(self.apply(srgb_to_lin3(srgb)))
    }
}

/// A control in a music session that people talk about by name.
pub struct Role {
    pub id: &'static str,
    pub label: &'static str,
    pub hex: &'static str,
}

/// Default colors of common Logic Pro / Pro Tools controls. The assistant pins
/// these by id; on a real screen a pin also catches nearby shades.
pub const ROLES: [Role; 18] = [
    Role { id: "record", label: "Record button & armed tracks", hex: "#e5322d" },
    Role { id: "play", label: "Play button", hex: "#3bbf4a" },
    Role { id: "cycle", label: "Cycle / loop range", hex: "#e8c33a" },
    Role { id: "solo", label: "Solo", hex: "#f2d23c" },
    Role { id: "mute", label: "Mute", hex: "#2fa9d9" },
    Role { id: "input", label: "Input monitoring", hex: "#e98a2c" },
    Role { id: "meterLow", label: "Meter: safe level", hex: "#34c759" },
    Role { id: "meterMid", label: "Meter: getting hot", hex: "#f4d03f" },
    Role { id: "meterClip", label: "Meter: clipping", hex: "#ff3b30" },
    Role { id: "automation", label: "Volume automation line", hex: "#a6e05a" },
    Role { id: "tKick", label: "Track color: Kick (red)", hex: "#d94b4b" },
    Role { id: "tSnare", label: "Track color: Snare (orange)", hex: "#e58a3a" },
    Role { id: "tBass", label: "Track color: Bass (yellow)", hex: "#c9b037" },
    Role { id: "tKeys", label: "Track color: Keys (green)", hex: "#6cbf4f" },
    Role { id: "tGtr", label: "Track color: Guitar (teal)", hex: "#3fa88c" },
    Role { id: "tVox", label: "Track color: Vocal (blue)", hex: "#3f86d9" },
    Role { id: "tBgv", label: "Track color: Backing vocals (purple)", hex: "#8e5bd6" },
    Role { id: "tFx", label: "Track color: FX (pink)", hex: "#d45ba8" },
];

pub fn role(id: &str) -> Option<&'static Role> {
    ROLES.iter().find(|r| r.id == id)
}

/// Okabe-Ito colors, which stay apart for nearly every kind of color vision.
pub mod safe {
    pub const ORANGE: &str = "#e69f00";
    pub const SKY: &str = "#56b4e9";
    pub const BLUISH_GREEN: &str = "#009e73";
    pub const YELLOW: &str = "#f0e442";
    pub const BLUE: &str = "#0072b2";
    pub const VERMILLION: &str = "#d55e00";
    pub const REDDISH_PURPLE: &str = "#cc79a7";
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_profile_is_identity() {
        let p = Profile::default();
        assert!(p.is_identity());
        let t = p.transform();
        for c in [[0.1, 0.5, 0.9], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]] {
            let o = t.apply(c);
            for i in 0..3 {
                assert!((o[i] - c[i]).abs() < 1e-6, "{c:?} -> {o:?}");
            }
        }
    }

    #[test]
    fn greys_survive_hue_changes() {
        let mut p = Profile::default();
        p.settings.daltonize = 1.0;
        p.settings.red_shift = -40.0;
        p.settings.green_shift = 40.0;
        p.settings.rg_split = 0.8;
        let t = p.transform();
        for g in [0.0, 0.2, 0.5, 1.0] {
            let o = t.apply([g, g, g]);
            for v in o {
                assert!((v - g).abs() < 1e-3, "grey {g} -> {o:?}");
            }
        }
    }

    #[test]
    fn pinned_color_lands_on_target() {
        let mut p = Profile::default();
        p.anchors.insert("solo".into(), Anchor { from: "#f2d23c".into(), to: "#0072b2".into(), label: "Solo".into() });
        let out = lin_to_hex(p.transform().apply(hex_to_lin("#f2d23c").unwrap()));
        assert_eq!(out, "#0072b2");
        // Colors far away are left alone.
        let far = lin_to_hex(p.transform().apply(hex_to_lin("#8e5bd6").unwrap()));
        assert_eq!(far, "#8e5bd6");
    }

    #[test]
    fn json_matches_tuner_page_format() {
        let js = r##"{"S":{"type":"protan","severity":0.9,"daltonize":0.5,"rgSplit":0.15,"bySplit":0,"redShift":-20,"greenShift":22,"yellowShift":0,"blueShift":0,"saturation":1,"contrast":1,"focus":0.08},
            "anchors":{"solo":{"from":"#f2d23c","to":"#f0e442","label":"Solo"}}}"##;
        let p = Profile::from_json(js).unwrap();
        assert_eq!(p.settings.cvd, CvdType::Protan);
        assert_eq!(p.settings.red_shift, -20.0);
        assert_eq!(p.anchors.len(), 1);
        let again = Profile::from_json(&p.to_json()).unwrap();
        assert_eq!(again, p);
    }

    #[test]
    fn out_of_range_values_are_clamped() {
        let p = Profile::from_json(r#"{"S":{"daltonize":7,"redShift":-500}}"#).unwrap();
        assert_eq!(p.settings.daltonize, 1.0);
        assert_eq!(p.settings.red_shift, -60.0);
    }

    #[test]
    fn matches_javascript_preview() {
        // Values computed by the tuner page's JavaScript for the same profile.
        let mut p = Profile::default();
        p.settings.daltonize = 0.5;
        p.settings.rg_split = 0.15;
        p.settings.red_shift = -20.0;
        p.settings.green_shift = 22.0;
        let t = p.transform();
        let got: Vec<String> = ["#e5322d", "#3bbf4a", "#f2d23c", "#2fa9d9"]
            .iter()
            .map(|h| lin_to_hex(t.apply(hex_to_lin(h).unwrap())))
            .collect();
        assert_eq!(got, crate::testdata::JS_EXPECTED.to_vec());
    }
}
