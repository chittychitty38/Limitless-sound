//! Measures the offline helper on people's descriptions of what they see (the .tsv files here),
//! the way its unit tests check it: by what each answer changes. A red-green answer moves reds
//! toward pink and greens toward blue-green, "too strong" eases everything back, "Solo and Mute"
//! pins both, and so on. Shared by tests/descriptions.rs (floors CI holds the helper to) and
//! examples/helper_report.rs (the numbers, and what it got wrong on the seen sets).

#![allow(dead_code)]

use std::collections::BTreeMap;
use std::path::Path;

use color_core::helper::{HelperState, Suggestion};
use color_core::lang::Lang;
use color_core::{CvdType, Profile};

pub struct Case {
    pub expect: String,
    pub context: String,
    pub who: String,
    pub text: String,
}

/// The sets: English and Spanish, seen (the rules were written against them) and held out.
pub const SETS: [(&str, Lang); 4] = [("en-seen", Lang::En), ("en-held", Lang::En), ("es-seen", Lang::Es), ("es-held", Lang::Es)];

pub fn load(name: &str) -> Vec<Case> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/descriptions").join(format!("{name}.tsv"));
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    text.lines()
        .filter(|l| !l.trim().is_empty() && !l.starts_with('#'))
        .map(|l| {
            let f: Vec<&str> = l.splitn(4, '\t').collect();
            assert_eq!(f.len(), 4, "{name}: expected 4 tab-separated fields in {l:?}");
            Case { expect: f[0].into(), context: f[1].into(), who: f[2].into(), text: f[3].into() }
        })
        .collect()
}

/// What happened before the person said this: nothing yet, or the helper's red-green change.
const CONTEXT_RG: &str = "red and green look the same";

/// The helper's answer to one description, and what that answer did.
pub fn run(case: &Case, lang: Lang) -> (&'static str, Suggestion) {
    let mut p = Profile::default();
    let start = p.clone();
    let mut state = HelperState::default();
    match case.context.as_str() {
        "-" => {}
        "rg" => {
            color_core::helper::offline_reply_in(CONTEXT_RG, &p, &mut state, Lang::En).apply_to(&mut p);
        }
        other => panic!("unknown context {other}"),
    }
    let before = p.clone();
    let s = color_core::helper::offline_reply_in(&case.text, &p, &mut state, lang);
    let mut after = p.clone();
    s.apply_to(&mut after);
    (outcome(&start, &before, &s, &after), s)
}

/// What an answer did, in the words of the .tsv files.
pub fn outcome(start: &Profile, before: &Profile, s: &Suggestion, after: &Profile) -> &'static str {
    let (b, a) = (&before.settings, &after.settings);
    if s.anchors.contains_key("solo") && s.anchors.contains_key("mute") {
        return "solo-mute";
    }
    if ["meterLow", "meterMid", "meterClip"].iter().any(|k| s.anchors.contains_key(*k)) {
        return "meters";
    }
    if a.cvd == CvdType::Protan && a.rg_split > b.rg_split {
        return "protan";
    }
    if a.cvd == CvdType::Tritan && a.by_split > b.by_split {
        return "by";
    }
    let (dr, dg) = (a.red_shift - b.red_shift, a.green_shift - b.green_shift);
    if dr < 0.0 && dg > 0.0 {
        // A first red-green step moves reds 20°; going further moves them 30°.
        return if dr <= -25.0 { "rg+" } else { "rg" };
    }
    if before != start && a == &start.settings && after.anchors == start.anchors {
        return "undo";
    }
    if a.daltonize < b.daltonize {
        return "less";
    }
    if a.daltonize > b.daltonize || a.saturation > b.saturation {
        return "more";
    }
    if a == b && after.anchors == before.anchors {
        return if s.kind == "ask" { "ask" } else { "keep" };
    }
    "other"
}

#[derive(Default)]
pub struct Score {
    pub right: usize,
    pub total: usize,
    /// expected outcome → (right, total)
    pub by_expect: BTreeMap<String, (usize, usize)>,
    /// who (region and form, dictation, typos) → (right, total)
    pub by_who: BTreeMap<String, (usize, usize)>,
    pub misses: Vec<(String, String, String)>,
}

impl Score {
    pub fn percent(&self) -> f64 {
        100.0 * self.right as f64 / self.total.max(1) as f64
    }
}

pub fn score(name: &str, lang: Lang) -> Score {
    let mut sc = Score::default();
    for case in load(name) {
        let (got, s) = run(&case, lang);
        let ok = got == case.expect;
        sc.total += 1;
        sc.right += ok as usize;
        let e = sc.by_expect.entry(case.expect.clone()).or_default();
        e.0 += ok as usize;
        e.1 += 1;
        let w = sc.by_who.entry(case.who.clone()).or_default();
        w.0 += ok as usize;
        w.1 += 1;
        if !ok {
            sc.misses.push((case.text.clone(), case.expect.clone(), format!("{got}: {} {}", s.reply, s.question)));
        }
    }
    sc
}
