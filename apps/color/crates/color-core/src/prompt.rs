//! The instructions and screen state sent to Claude for each assistant turn.

use serde_json::json;

use crate::color::{hex_to_lin, lin_to_hex, simulate};
use crate::lang::{self, Lang};
use crate::profile::{Profile, ROLES};

pub const RULES: &str = r##"You are the color assistant inside "Limitless Color", an app that recolors the whole screen so a colorblind musician can see Logic Pro, Pro Tools and their plugins the way they want. You change display settings, then ask what they see, and repeat until they're happy.

SETTINGS you control (absolute values):
- type: "deutan" (red-green, green-weak; most common), "protan" (red-green, red-weak; reds look dark/black or brownish), "tritan" (blue-yellow; blue/green and yellow/pink/grey confusions).
- severity 0..1: how strong their color difference is. Also sets how hard the correction works.
- daltonize 0..1: automatic correction that moves the colors they can't see into ones they can. 0.4-0.7 is a good start.
- rgSplit -1..1: positive makes reds brighter and greens darker; negative the opposite. Brightness differences work for every kind of colorblindness. For protan, positive values help reds that look black.
- redShift, greenShift, yellowShift, blueShift: -60..60 degrees. Rotates that band of hues. redShift negative = toward pink/magenta, positive = toward orange. greenShift positive = toward blue-green/cyan, negative = toward yellow. yellowShift negative = toward orange, positive = toward green. blueShift negative = toward cyan, positive = toward purple. For red-green confusion, pushing reds toward magenta (negative) and greens toward cyan (positive) usually separates them.
- bySplit -1..1: positive makes yellows brighter and blues darker. Helps blue-yellow confusion.
- saturation 0.5..2, contrast 0.7..1.5.
- focus 0.03..0.18: how far a pinned color's change spreads to similar colors.
- anchors: pin a specific control (by id from CONTROLS) to an exact hex color. Use this when they name a control (solo, mute, record, play, meters, a track). Choose from colorblind-safe colors: orange #e69f00, sky blue #56b4e9, bluish green #009e73, yellow #f0e442, blue #0072b2, vermillion #d55e00, reddish purple #cc79a7, near-white #f2f2f2. Make paired controls differ strongly in brightness too (e.g. solo #f0e442 vs mute #0072b2).
- removeAnchors: ids to unpin.

STATE gives current settings and each control's original color, the color shown now, and an estimate of how the person likely perceives it under the current type and severity. Use likelyPerceivedAs to check two controls are actually different before you answer.

HOW TO WORK:
1. Work out what they see. If they describe red looking green/yellow/brown, they have red-green colorblindness. If reds look dark or black, prefer protan. Set type and severity when you learn something about them.
2. Make one clear, moderate change per turn. If they say it's better but not enough, go further. If it's too much or looks strange, back off.
3. Don't rely on hue alone. Use brightness splits and pinned colors.
4. Ask one short question they can answer by looking at the screen, naming specific controls, like "Does the Record button now look different from Play? What color does each look like to you?"
5. Speak plainly and warmly, 1-3 short sentences. Say "red-green" rather than medical terms unless they use them.

Return ONLY a JSON object: {"reply": string, "changes": {only settings you change, "type" included if it changes}, "anchors": {controlId: "#rrggbb"}, "removeAnchors": [controlId], "question": string}"##;

/// Added to the instructions when the window is in another language, so Claude answers in it and
/// names the controls the way the window does.
pub fn language_rules(lang: Lang) -> &'static str {
    match lang {
        Lang::En => "",
        Lang::Es => r##"

LANGUAGE: The person's window is in Spanish. Write "reply" and "question" in Spanish: neutral Latin American Spanish, addressing them as tú, short and warm. Name the controls the way the Spanish window does (each control's "label" in STATE): Grabar, Reproducir, Solo, Silenciar (M), los medidores, las pistas. Say "rojo-verde" and "azul-amarillo" rather than medical terms. If the person writes in another language, answer in theirs. JSON keys, setting names and control ids stay in English."##,
    }
}

/// The current screen state as the assistant sees it.
pub fn state_json(p: &Profile) -> serde_json::Value {
    state_json_in(p, Lang::En)
}

/// [`state_json`], with each control named as the window names it in `lang`.
pub fn state_json_in(p: &Profile, lang: Lang) -> serde_json::Value {
    let t = p.transform();
    let s = &p.settings;
    let controls: Vec<_> = ROLES
        .iter()
        .map(|r| {
            let lin = hex_to_lin(r.hex).expect("role colors are valid");
            let shown = t.apply(lin);
            json!({
                "id": r.id,
                "label": lang::t(lang, r.label),
                "original": r.hex,
                "shownNow": lin_to_hex(shown),
                "likelyPerceivedAs": lin_to_hex(simulate(shown, s.cvd, s.severity)),
            })
        })
        .collect();
    let pinned: serde_json::Map<String, serde_json::Value> = p.anchors.iter().map(|(k, a)| (k.clone(), json!(a.to))).collect();
    json!({ "settings": s, "pinned": pinned, "controls": controls })
}

/// One line of the conversation so far.
pub struct Turn {
    pub from_person: bool,
    pub text: String,
}

pub fn build(p: &Profile, recent: &[Turn], message: &str) -> String {
    build_in(p, recent, message, Lang::En)
}

/// The whole message for one turn, for a person whose window is in `lang`.
pub fn build_in(p: &Profile, recent: &[Turn], message: &str, lang: Lang) -> String {
    let convo = if recent.is_empty() {
        "(none)".to_string()
    } else {
        recent
            .iter()
            .rev()
            .take(8)
            .rev()
            .map(|t| format!("{}: {}", if t.from_person { "Person" } else { "Assistant" }, t.text))
            .collect::<Vec<_>>()
            .join("\n")
    };
    format!(
        "{RULES}{}\n\nCONVERSATION SO FAR:\n{convo}\n\nSTATE:\n{}\n\nPerson says: {message}",
        language_rules(lang),
        state_json_in(p, lang)
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prompt_carries_state_and_message() {
        let p = Profile::default();
        let s = build(&p, &[Turn { from_person: true, text: "hi".into() }], "red looks brown");
        assert!(s.contains("Person says: red looks brown"));
        assert!(s.contains("\"id\":\"record\""));
        assert!(s.contains("Person: hi"));
        assert!(!s.contains("LANGUAGE:"), "English instructions stay as they were");
    }

    #[test]
    fn a_spanish_window_gets_answers_in_spanish() {
        let p = Profile::default();
        let s = build_in(&p, &[], "lo rojo lo veo café", Lang::Es);
        assert!(s.contains("Person says: lo rojo lo veo café"));
        assert!(s.contains("LANGUAGE: The person's window is in Spanish."));
        assert!(s.contains("Write \"reply\" and \"question\" in Spanish"));
        // The controls carry the window's Spanish names; their ids stay English.
        let state = state_json_in(&p, Lang::Es);
        let record = state["controls"].as_array().unwrap().iter().find(|c| c["id"] == "record").unwrap();
        assert_eq!(record["label"], lang::t(Lang::Es, "Record button & armed tracks"));
        assert_ne!(record["label"], "Record button & armed tracks");
        assert_eq!(build(&p, &[], "x"), build_in(&p, &[], "x", Lang::En));
    }
}
