//! "Make it clear for me": searches the fader settings for the profile that
//! makes the controls musicians rely on look most different to this person,
//! while keeping the rest of the screen looking natural.
//!
//! The search scores a profile by simulating how the person sees each control
//! after correction (Machado 2009 at their type and severity) and measuring the
//! distance between controls that must never be confused, such as Record and
//! Play, Solo and Mute, or the stages of a level meter.

use serde::Serialize;

use crate::color::{hex_to_lin, lin_to_oklab, simulate, CvdType, Rgb};
use crate::profile::{role, safe, Anchor, Profile, Settings};

/// Pairs of controls that must look different, with how much it matters.
pub const KEY_PAIRS: [(&str, &str, f64); 9] = [
    ("record", "play", 3.0),
    ("solo", "mute", 3.0),
    ("meterLow", "meterClip", 3.0),
    ("meterLow", "meterMid", 2.0),
    ("meterMid", "meterClip", 2.0),
    ("record", "input", 1.5),
    ("tKick", "tKeys", 1.5),
    ("tVox", "tBgv", 1.0),
    ("tGtr", "tVox", 1.0),
];

const TRACKS: [&str; 8] = ["tKick", "tSnare", "tBass", "tKeys", "tGtr", "tVox", "tBgv", "tFx"];

/// OKLab distance at which two colors are comfortably told apart at a glance.
const CLEAR: f64 = 0.12;

/// How one pair of controls looks before and after tuning, as this person sees them.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PairReport {
    pub a: String,
    pub b: String,
    pub label: String,
    /// Perceived difference, 0 = identical; about 0.12 and up is clear at a glance.
    pub before: f64,
    pub after: f64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TuneResult {
    pub profile: Profile,
    pub pairs: Vec<PairReport>,
    /// Pairs that were still hard to tell apart and got pinned to safe colors.
    pub pinned: Vec<String>,
}

fn perceived(p: &Profile, cvd: CvdType, severity: f64) -> impl Fn(Rgb) -> Rgb {
    let t = p.transform();
    move |lin| lin_to_oklab(simulate(t.apply(lin), cvd, severity))
}

fn dist(a: Rgb, b: Rgb) -> f64 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

fn role_lin(id: &str) -> Rgb {
    hex_to_lin(role(id).expect("known role").hex).expect("valid hex")
}

/// Perceived distance of every key pair under a profile.
pub fn pair_distances(p: &Profile, cvd: CvdType, severity: f64) -> Vec<f64> {
    let see = perceived(p, cvd, severity);
    KEY_PAIRS.iter().map(|(a, b, _)| dist(see(role_lin(a)), see(role_lin(b)))).collect()
}

fn grid() -> Vec<Rgb> {
    let steps = [0.1, 0.35, 0.6, 0.85];
    let mut g = vec![];
    for &r in &steps {
        for &gg in &steps {
            for &b in &steps {
                g.push([r, gg, b].map(crate::color::srgb_to_linear));
            }
        }
    }
    g
}

/// Higher is better.
fn score(p: &Profile, cvd: CvdType, severity: f64, grid: &[Rgb]) -> f64 {
    let see = perceived(p, cvd, severity);
    // Separation of key pairs, with diminishing returns past "clear".
    let mut sep = 0.0;
    let mut worst = f64::MAX;
    for (a, b, w) in KEY_PAIRS {
        let d = dist(see(role_lin(a)), see(role_lin(b)));
        // Full credit once a pair is comfortably clear; past that, naturalness wins.
        sep += w * (d / (1.5 * CLEAR)).min(1.0);
        worst = worst.min(d / CLEAR);
    }
    // Every track color should stay distinct from every other.
    let tracks: Vec<Rgb> = TRACKS.iter().map(|id| see(role_lin(id))).collect();
    let mut track_sep = 0.0;
    for i in 0..tracks.len() {
        for j in i + 1..tracks.len() {
            track_sep += (dist(tracks[i], tracks[j]) / CLEAR).min(1.0);
        }
    }
    // Naturalness: how far colors move from the original, as anyone would see them.
    let t = p.transform();
    let drift: f64 = grid.iter().map(|&c| dist(lin_to_oklab(t.apply(c)), lin_to_oklab(c))).sum::<f64>() / grid.len() as f64;
    sep + 0.25 * track_sep + 2.0 * worst.min(1.0) - 6.0 * drift
}

struct Knob {
    key: &'static str,
    lo: f64,
    hi: f64,
    step: f64,
}

const KNOBS: [Knob; 8] = [
    Knob { key: "daltonize", lo: 0.0, hi: 1.0, step: 0.25 },
    Knob { key: "rgSplit", lo: -0.6, hi: 0.9, step: 0.3 },
    Knob { key: "redShift", lo: -45.0, hi: 25.0, step: 15.0 },
    Knob { key: "greenShift", lo: -25.0, hi: 45.0, step: 15.0 },
    Knob { key: "yellowShift", lo: -30.0, hi: 30.0, step: 12.0 },
    Knob { key: "blueShift", lo: -30.0, hi: 40.0, step: 12.0 },
    Knob { key: "bySplit", lo: -0.6, hi: 0.9, step: 0.3 },
    Knob { key: "saturation", lo: 1.0, hi: 1.25, step: 0.1 },
];

fn starting_points(cvd: CvdType) -> Vec<Settings> {
    let mut base = Settings { cvd, ..Settings::default() };
    let mut v = vec![base.clone()];
    match cvd {
        CvdType::Protan | CvdType::Deutan => {
            base.daltonize = 0.5;
            base.red_shift = -20.0;
            base.green_shift = 20.0;
            base.rg_split = if cvd == CvdType::Protan { 0.4 } else { 0.2 };
            v.push(base.clone());
            base.daltonize = 0.8;
            base.red_shift = -35.0;
            base.green_shift = 35.0;
            v.push(base);
            // Darker reds, greens pushed toward teal, blues split from purples:
            // the shape that works best across red-green strengths.
            v.push(Settings {
                cvd,
                rg_split: -0.6,
                by_split: 0.3,
                green_shift: 30.0,
                blue_shift: -30.0,
                saturation: 1.15,
                ..Settings::default()
            });
        }
        CvdType::Tritan => {
            base.daltonize = 0.5;
            base.by_split = 0.4;
            base.blue_shift = 20.0;
            v.push(base.clone());
            base.daltonize = 0.8;
            base.by_split = 0.6;
            base.yellow_shift = -15.0;
            v.push(base);
        }
    }
    v
}

/// Finds the clearest natural-looking profile for this kind and strength of
/// color vision difference. Deterministic: the same input always gives the same profile.
pub fn auto_tune(cvd: CvdType, severity: f64) -> TuneResult {
    let severity = severity.clamp(0.1, 1.0);
    let g = grid();
    let before_profile = Profile { settings: Settings { cvd, severity, ..Settings::default() }, ..Profile::default() };
    let before = pair_distances(&before_profile, cvd, severity);

    let mut best: Option<(f64, Profile)> = None;
    for mut start in starting_points(cvd) {
        start.severity = severity;
        let mut p = Profile { settings: start, ..Profile::default() };
        let mut s = score(&p, cvd, severity, &g);
        // Coordinate search with shrinking steps.
        let mut scale = 1.0;
        while scale > 0.05 {
            let mut improved = false;
            for k in &KNOBS {
                for dir in [-1.0, 1.0] {
                    let cur = p.settings.get(k.key).unwrap_or(0.0);
                    let next = (cur + dir * k.step * scale).clamp(k.lo, k.hi);
                    if next == cur {
                        continue;
                    }
                    let mut q = p.clone();
                    q.settings.set(k.key, next);
                    let sq = score(&q, cvd, severity, &g);
                    if sq > s + 1e-6 {
                        p = q;
                        s = sq;
                        improved = true;
                    }
                }
            }
            if !improved {
                scale *= 0.5;
            }
        }
        if best.as_ref().map_or(true, |(bs, _)| s > *bs) {
            best = Some((s, p));
        }
    }
    let mut profile = best.expect("at least one start").1;
    // Round to what the faders show, so the numbers read cleanly.
    for k in &KNOBS {
        if let Some(v) = profile.settings.get(k.key) {
            let unit = if k.step >= 1.0 { 1.0 } else { 0.01 };
            profile.settings.set(k.key, (v / unit).round() * unit);
        }
    }
    profile.settings = profile.settings.clone().clamped();

    // Any key pair still hard to tell apart gets pinned to colorblind-safe colors.
    let mut pinned = vec![];
    let after = pair_distances(&profile, cvd, severity);
    let safe_pins: [(&str, &str, &str, &str); 3] = [
        ("solo", safe::YELLOW, "mute", safe::BLUE),
        ("record", safe::VERMILLION, "play", safe::BLUISH_GREEN),
        ("meterLow", safe::SKY, "meterClip", safe::VERMILLION),
    ];
    for (a, ca, b, cb) in safe_pins {
        let i = KEY_PAIRS.iter().position(|(x, y, _)| *x == a && *y == b).expect("pin pair is a key pair");
        if after[i] < CLEAR * 0.75 {
            let mut q = profile.clone();
            for (id, hex) in [(a, ca), (b, cb)] {
                let r = role(id).expect("known role");
                q.anchors.insert(id.into(), Anchor { from: r.hex.into(), to: hex.into(), label: r.label.into() });
            }
            if pair_distances(&q, cvd, severity)[i] > after[i] {
                profile = q;
                pinned.push(format!("{} and {}", role(a).unwrap().label, role(b).unwrap().label));
            }
        }
    }

    let after = pair_distances(&profile, cvd, severity);
    let pairs = KEY_PAIRS
        .iter()
        .zip(before.iter().zip(&after))
        .map(|((a, b, _), (&bf, &af))| PairReport {
            a: a.to_string(),
            b: b.to_string(),
            label: format!("{} vs {}", short(a), short(b)),
            before: bf,
            after: af,
        })
        .collect();
    TuneResult { profile, pairs, pinned }
}

fn short(id: &str) -> &'static str {
    match id {
        "record" => "Record",
        "play" => "Play",
        "solo" => "Solo",
        "mute" => "Mute",
        "meterLow" => "Meter safe",
        "meterMid" => "Meter hot",
        "meterClip" => "Meter clipping",
        "input" => "Input",
        "tKick" => "Red track",
        "tKeys" => "Green track",
        "tVox" => "Blue track",
        "tBgv" => "Purple track",
        "tGtr" => "Teal track",
        _ => "Control",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn worst(v: &[f64]) -> f64 {
        v.iter().cloned().fold(f64::MAX, f64::min)
    }

    #[test]
    fn tuning_makes_red_green_controls_clearly_different() {
        for cvd in [CvdType::Deutan, CvdType::Protan] {
            let r = auto_tune(cvd, 1.0);
            let before: Vec<f64> = r.pairs.iter().map(|p| p.before).collect();
            let after: Vec<f64> = r.pairs.iter().map(|p| p.after).collect();
            // Record vs Play and the meter stages are what red-green colorblind musicians struggle with most.
            let rp = &r.pairs[0];
            // Either the pair gets much clearer, or it was already clear (protan red reads as dark) and stays clear.
            let ok = rp.after > rp.before * 1.8 || (rp.before > 1.5 * CLEAR && rp.after > 0.95 * rp.before);
            assert!(ok, "{cvd:?} record/play {} -> {}", rp.before, rp.after);
            assert!(worst(&after) > worst(&before) * 1.5, "{cvd:?} worst {} -> {}", worst(&before), worst(&after));
            assert!(worst(&after) > 0.06, "{cvd:?} worst after {}", worst(&after));
        }
    }

    #[test]
    fn tuning_helps_blue_yellow() {
        let r = auto_tune(CvdType::Tritan, 1.0);
        let before: Vec<f64> = r.pairs.iter().map(|p| p.before).collect();
        let after: Vec<f64> = r.pairs.iter().map(|p| p.after).collect();
        assert!(worst(&after) > worst(&before), "{} -> {}", worst(&before), worst(&after));
    }

    #[test]
    fn mild_difference_gets_a_gentler_profile() {
        let strong = auto_tune(CvdType::Deutan, 1.0).profile;
        let mild = auto_tune(CvdType::Deutan, 0.3).profile;
        let drift = |p: &Profile| {
            let t = p.transform();
            grid().iter().map(|&c| dist(lin_to_oklab(t.apply(c)), lin_to_oklab(c))).sum::<f64>()
        };
        assert!(drift(&mild) <= drift(&strong) + 1e-9, "mild {} strong {}", drift(&mild), drift(&strong));
    }

    #[test]
    fn tuning_is_deterministic_and_keeps_greys() {
        let a = auto_tune(CvdType::Deutan, 0.8);
        let b = auto_tune(CvdType::Deutan, 0.8);
        assert_eq!(a.profile, b.profile);
        let o = a.profile.transform().apply([0.5, 0.5, 0.5]);
        for v in o {
            assert!((v - 0.5).abs() < 0.02, "{o:?}");
        }
    }
}
