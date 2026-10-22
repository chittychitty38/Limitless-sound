//! What the assistant can change, how its answers are checked, and the offline
//! helper that works without an internet connection or a Claude account.

use std::collections::BTreeMap;

use regex::Regex;
use serde::{Deserialize, Serialize};

use crate::color::{hex_to_srgb, CvdType};
use crate::profile::{role, safe, Anchor, Profile, RANGES};

/// One assistant turn: what it says, and what it changes.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Suggestion {
    pub reply: String,
    pub question: String,
    /// Absolute values for numeric settings, by JSON key.
    pub changes: BTreeMap<String, f64>,
    #[serde(rename = "type")]
    pub cvd: Option<CvdType>,
    /// Control id to the hex color it should show as.
    pub anchors: BTreeMap<String, String>,
    pub remove_anchors: Vec<String>,
}

impl Suggestion {
    /// Reads Claude's reply: a JSON object, possibly wrapped in prose or a code fence.
    /// Anything unknown or out of range is dropped or clamped.
    pub fn from_model_text(text: &str) -> Option<Suggestion> {
        let start = text.find('{')?;
        let end = text.rfind('}')?;
        let v: serde_json::Value = serde_json::from_str(text.get(start..=end)?).ok()?;
        let mut s = Suggestion {
            reply: v["reply"].as_str().unwrap_or_default().chars().take(800).collect(),
            question: v["question"].as_str().unwrap_or_default().chars().take(300).collect(),
            ..Default::default()
        };
        if let Some(ch) = v["changes"].as_object() {
            for (k, val) in ch {
                if k == "type" {
                    s.cvd = serde_json::from_value(val.clone()).ok();
                } else if let (Some(&(_, lo, hi)), Some(x)) = (RANGES.iter().find(|r| r.0 == k), val.as_f64()) {
                    s.changes.insert(k.clone(), x.clamp(lo, hi));
                }
            }
        }
        if let Some(an) = v["anchors"].as_object() {
            for (id, hex) in an {
                if let (Some(_), Some(h)) = (role(id), hex.as_str()) {
                    if hex_to_srgb(h).is_some() {
                        s.anchors.insert(id.clone(), h.to_lowercase());
                    }
                }
            }
        }
        if let Some(rm) = v["removeAnchors"].as_array() {
            s.remove_anchors = rm.iter().filter_map(|x| x.as_str().map(String::from)).collect();
        }
        if s.reply.is_empty() && s.changes.is_empty() && s.anchors.is_empty() && s.cvd.is_none() {
            return None;
        }
        Some(s)
    }

    /// Applies the suggestion and returns a short plain-language list of what changed.
    pub fn apply_to(&self, p: &mut Profile) -> Vec<String> {
        let mut done = vec![];
        if let Some(t) = self.cvd {
            if t != p.settings.cvd {
                p.settings.cvd = t;
                done.push(format!("Color vision: {}", t.plain_name()));
            }
        }
        for (k, &v) in &self.changes {
            let before = p.settings.get(k);
            if p.settings.set(k, v) && before != p.settings.get(k) {
                done.push(format!("{}: {}", label(k), fmt(k, p.settings.get(k).unwrap_or(v))));
            }
        }
        for (id, to) in &self.anchors {
            if let Some(r) = role(id) {
                p.anchors.insert(id.clone(), Anchor { from: r.hex.into(), to: to.clone(), label: r.label.into() });
                done.push(format!("Pinned {}", r.label));
            }
        }
        for id in &self.remove_anchors {
            if let Some(a) = p.anchors.remove(id) {
                done.push(format!("Unpinned {}", if a.label.is_empty() { id } else { &a.label }));
            }
        }
        done
    }
}

pub fn label(key: &str) -> &'static str {
    match key {
        "severity" => "How strong the difference is",
        "daltonize" => "Color correction",
        "rgSplit" => "Red vs green brightness",
        "bySplit" => "Blue vs yellow brightness",
        "redShift" => "Move reds",
        "greenShift" => "Move greens",
        "yellowShift" => "Move yellows",
        "blueShift" => "Move blues",
        "saturation" => "Color strength",
        "contrast" => "Light/dark contrast",
        "focus" => "Pin reach",
        _ => "Setting",
    }
}

fn fmt(key: &str, v: f64) -> String {
    match key {
        "severity" | "daltonize" => format!("{}%", (v * 100.0).round()),
        k if k.ends_with("Shift") => format!("{:+}°", v.round()),
        "saturation" | "contrast" => format!("{v:.2}×"),
        _ => format!("{v:+.2}"),
    }
}

/// Remembers the direction of the last change so "still the same" can go further.
#[derive(Debug, Default, Clone)]
pub struct HelperState {
    last: Option<&'static str>,
}

/// Rule-based helper for when Claude isn't available. It understands the common
/// ways people describe red-green and blue-yellow confusion and named controls.
pub fn offline_reply(text: &str, p: &Profile, state: &mut HelperState) -> Suggestion {
    let s = text.to_lowercase();
    let has = |pat: &str| Regex::new(&format!(r"\b({pat})")).map(|r| r.is_match(&s)).unwrap_or(false);
    let red = has("red|record|clip");
    let green = has("green|play");
    let yellow = has("yellow|gold");
    let brown = has("brown|olive|khaki");
    let orange = has("orange");
    let blue = has("blue|navy|cyan|teal");
    let purple = has("purple|violet|pink|magenta");
    let grey = has("gr[ae]y|white");
    let less = has("too much|too strong|less|weird looking|ugly|natural|harsh|tone it");
    let more = has("still|more|not enough|stronger|same|can't|cannot|hard");
    let st = &p.settings;
    let mut r = Suggestion::default();
    let ch = |r: &mut Suggestion, k: &str, v: f64| {
        r.changes.insert(k.to_string(), v);
    };

    if less {
        for k in ["daltonize", "rgSplit", "bySplit", "redShift", "greenShift", "yellowShift", "blueShift"] {
            ch(&mut r, k, st.get(k).unwrap_or(0.0) * 0.6);
        }
        ch(&mut r, "saturation", 1.0 + (st.saturation - 1.0) * 0.6);
        r.reply = "I eased everything back by about a third so it looks more natural.".into();
        r.question = "Can you still tell apart the colors that were giving you trouble?".into();
        return r;
    }
    if has("solo") && has("mute") {
        r.anchors.insert("solo".into(), safe::YELLOW.into());
        r.anchors.insert("mute".into(), safe::BLUE.into());
        r.reply = "I pinned Solo to a bright yellow and Mute to a deep blue, so they differ in brightness as well as color.".into();
        r.question = "Do the S and M buttons look clearly different now?".into();
        return r;
    }
    if has("meter") {
        r.anchors.insert("meterLow".into(), safe::SKY.into());
        r.anchors.insert("meterMid".into(), safe::YELLOW.into());
        r.anchors.insert("meterClip".into(), safe::VERMILLION.into());
        ch(&mut r, "rgSplit", st.rg_split + 0.2);
        r.reply = "I changed the meters to blue for safe, yellow for hot and orange-red for clipping. Those three stay apart for most kinds of colorblindness.".into();
        r.question = "Looking at a level meter, can you see where blue turns to yellow and then to red?".into();
        return r;
    }
    if red && has("black|dark") {
        r.cvd = Some(CvdType::Protan);
        ch(&mut r, "severity", st.severity.max(0.8));
        ch(&mut r, "daltonize", st.daltonize.max(0.5));
        ch(&mut r, "rgSplit", st.rg_split + 0.35);
        ch(&mut r, "redShift", st.red_shift - 15.0);
        r.reply = "Reds that look dark usually mean the red-sensing part of the eye is weaker. I made reds brighter and nudged them toward pink.".into();
        r.question = "Do red things, like the Record button, look brighter now? What color do they look like?".into();
        return r;
    }
    if (red || green) && ((green && red) || yellow || brown || orange) && !blue {
        let step = if more && state.last == Some("rg") { 1.5 } else { 1.0 };
        state.last = Some("rg");
        if st.cvd == CvdType::Tritan {
            r.cvd = Some(CvdType::Deutan);
        }
        ch(&mut r, "daltonize", st.daltonize.max(0.5) * if step > 1.0 { 1.25 } else { 1.0 });
        ch(&mut r, "redShift", st.red_shift - 20.0 * step);
        ch(&mut r, "greenShift", st.green_shift + 22.0 * step);
        ch(&mut r, "rgSplit", st.rg_split + 0.15 * step);
        r.reply = if step > 1.0 {
            "I pushed further: reds more toward pink, greens more toward blue-green.".into()
        } else {
            "That sounds like red-green colorblindness. I moved reds toward pink, greens toward blue-green, and made reds a bit brighter so they stand apart.".into()
        };
        r.question = "Compare the Record button and the Play button. Do they look different now? What color does each look like to you?".into();
        return r;
    }
    if (blue && (green || purple)) || (yellow && (purple || grey)) {
        state.last = Some("by");
        r.cvd = Some(CvdType::Tritan);
        ch(&mut r, "severity", st.severity.max(0.7));
        ch(&mut r, "daltonize", st.daltonize.max(0.5));
        ch(&mut r, "bySplit", st.by_split + 0.3);
        ch(&mut r, "blueShift", st.blue_shift + 15.0);
        ch(&mut r, "greenShift", st.green_shift - 12.0);
        r.reply = "That points to blue-yellow colorblindness. I made yellows brighter than blues and pulled blues toward purple, away from greens.".into();
        r.question = "Do blue and teal tracks look different now?".into();
        return r;
    }
    if more {
        ch(&mut r, "daltonize", st.daltonize + 0.2);
        ch(&mut r, "saturation", st.saturation + 0.15);
        r.reply = "I turned the correction up and made colors a little bolder.".into();
        r.question = "Which two things still look the same to you?".into();
        return r;
    }
    r.reply = "I'm not sure what to change yet. Try naming two things that look the same to you, for example \"the Record button and the Play button look the same\" or \"red looks brown\".".into();
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn red_looks_green_turns_on_red_green_correction() {
        let mut p = Profile::default();
        let mut st = HelperState::default();
        let s = offline_reply("What is supposed to be red I see as weird green/yellow", &p, &mut st);
        assert!(s.changes["daltonize"] >= 0.5);
        assert!(s.changes["redShift"] < 0.0);
        assert!(s.changes["greenShift"] > 0.0);
        let done = s.apply_to(&mut p);
        assert!(!done.is_empty());
        // Saying it's still the same pushes further in the same direction.
        let s2 = offline_reply("they still look the same red and green", &p, &mut st);
        assert!(s2.changes["redShift"] < p.settings.red_shift);
    }

    #[test]
    fn too_strong_backs_off() {
        let mut p = Profile::default();
        p.settings.daltonize = 1.0;
        p.settings.red_shift = -40.0;
        let s = offline_reply("that's too strong", &p, &mut HelperState::default());
        s.apply_to(&mut p);
        assert!(p.settings.daltonize < 1.0);
        assert!(p.settings.red_shift > -40.0);
    }

    #[test]
    fn solo_mute_pins_both() {
        let mut p = Profile::default();
        let s = offline_reply("I can't tell solo from mute", &p, &mut HelperState::default());
        s.apply_to(&mut p);
        assert!(p.anchors.contains_key("solo") && p.anchors.contains_key("mute"));
    }

    #[test]
    fn parses_model_json_and_drops_junk() {
        let text = "Sure!\n```json\n{\"reply\":\"Done.\",\"changes\":{\"daltonize\":3,\"type\":\"protan\",\"bogus\":1},\"anchors\":{\"solo\":\"#F0E442\",\"nope\":\"#000000\",\"mute\":\"red\"},\"removeAnchors\":[\"play\"],\"question\":\"Better?\"}\n```";
        let s = Suggestion::from_model_text(text).unwrap();
        assert_eq!(s.changes.get("daltonize"), Some(&1.0));
        assert!(!s.changes.contains_key("bogus"));
        assert_eq!(s.cvd, Some(CvdType::Protan));
        assert_eq!(s.anchors.len(), 1);
        assert_eq!(s.anchors["solo"], "#f0e442");
        assert!(Suggestion::from_model_text("no json here").is_none());
    }
}
