//! What the assistant can change, how its answers are checked, and the offline
//! helper that works without an internet connection or a Claude account.

use std::collections::BTreeMap;
use std::sync::OnceLock;

use regex::Regex;
use serde::{Deserialize, Serialize};

use crate::color::{hex_to_srgb, CvdType};
use crate::lang::{t, tf, Lang};
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
    /// What the offline helper made of the message ("rg", "less", "keep", "ask"...), for measuring it.
    #[serde(skip)]
    pub kind: &'static str,
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
        self.apply_in(p, Lang::En)
    }

    /// [`Suggestion::apply_to`], with the list of what changed in `lang`.
    pub fn apply_in(&self, p: &mut Profile, lang: Lang) -> Vec<String> {
        let mut done = vec![];
        if let Some(c) = self.cvd {
            if c != p.settings.cvd {
                p.settings.cvd = c;
                done.push(tf(lang, said::COLOR_VISION, &[("name", &t(lang, c.plain_name()))]));
            }
        }
        for (k, &v) in &self.changes {
            let before = p.settings.get(k);
            if p.settings.set(k, v) && before != p.settings.get(k) {
                done.push(format!("{}: {}", t(lang, label(k)), fmt(k, p.settings.get(k).unwrap_or(v))));
            }
        }
        for (id, to) in &self.anchors {
            if let Some(r) = role(id) {
                p.anchors.insert(id.clone(), Anchor { from: r.hex.into(), to: to.clone(), label: r.label.into() });
                done.push(tf(lang, said::PINNED, &[("name", &t(lang, r.label))]));
            }
        }
        for id in &self.remove_anchors {
            if let Some(a) = p.anchors.remove(id) {
                let name = if a.label.is_empty() { id.clone() } else { t(lang, &a.label) };
                done.push(tf(lang, said::UNPINNED, &[("name", &name)]));
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

/// What the helper remembers between turns: the direction of its last change, so "still the
/// same" can go further, and the colors before it, so "that's worse" can put them back.
#[derive(Debug, Default, Clone)]
pub struct HelperState {
    last: Option<&'static str>,
    /// The profile before the helper's last change, and the profile that change made.
    undo: Option<(Profile, Profile)>,
}

/// Everything the helper says, in English. The Spanish is in the tuner window's table, with
/// the rest of Color's words (see `lang`).
pub mod said {
    pub const EASED: &str = "I eased everything back by about a third so it looks more natural.";
    pub const STILL_TELL: &str = "Can you still tell apart the colors that were giving you trouble?";
    pub const UNDONE: &str = "I put the colors back the way they were before my last change.";
    pub const TRY_ANOTHER: &str = "Which colors or buttons still look alike? I'll try another way.";
    pub const DONE: &str = "Great. Your colors stay like this, and they're saved. Tell me any time something looks off.";
    pub const BETTER: &str = "Good, I'll keep it like this.";
    pub const ANYTHING_ELSE: &str = "Is anything still hard to tell apart?";
    pub const SOLO_MUTE: &str = "I pinned Solo to a bright yellow and Mute to a deep blue, so they differ in brightness as well as color.";
    pub const SOLO_MUTE_Q: &str = "Do the S and M buttons look clearly different now?";
    pub const METERS: &str = "I changed the meters to blue for safe, yellow for hot and orange-red for clipping. Those three stay apart for most kinds of colorblindness.";
    pub const METERS_Q: &str = "Looking at a level meter, can you see where blue turns to yellow and then to red?";
    pub const PROTAN: &str = "Reds that look dark usually mean the red-sensing part of the eye is weaker. I made reds brighter and nudged them toward pink.";
    pub const PROTAN_Q: &str = "Do red things, like the Record button, look brighter now? What color do they look like?";
    pub const RG: &str = "That sounds like red-green colorblindness. I moved reds toward pink, greens toward blue-green, and made reds a bit brighter so they stand apart.";
    pub const RG_FURTHER: &str = "I pushed further: reds more toward pink, greens more toward blue-green.";
    pub const RG_Q: &str = "Compare the Record button and the Play button. Do they look different now? What color does each look like to you?";
    pub const BY: &str = "That points to blue-yellow colorblindness. I made yellows brighter than blues and pulled blues toward purple, away from greens.";
    pub const BY_FURTHER: &str = "I pushed further: yellows brighter still, and blues more toward purple.";
    pub const BY_Q: &str = "Do blue and teal tracks look different now?";
    pub const MORE: &str = "I turned the correction up and made colors a little bolder.";
    pub const MORE_Q: &str = "Which two things still look the same to you?";
    pub const NOT_SURE: &str = "I'm not sure what to change yet. Try naming two things that look the same to you, for example {example1} or {example2}.";
    pub const EXAMPLE_1: &str = "the Record button and the Play button look the same";
    pub const EXAMPLE_2: &str = "red looks brown";
    /// What changed, in the list under a reply.
    pub const COLOR_VISION: &str = "Color vision: {name}";
    pub const PINNED: &str = "Pinned {name}";
    pub const UNPINNED: &str = "Unpinned {name}";

    pub const ALL: [&str; 27] = [
        EASED, STILL_TELL, UNDONE, TRY_ANOTHER, DONE, BETTER, ANYTHING_ELSE, SOLO_MUTE, SOLO_MUTE_Q, METERS, METERS_Q,
        PROTAN, PROTAN_Q, RG, RG_FURTHER, RG_Q, BY, BY_FURTHER, BY_Q, MORE, MORE_Q, NOT_SURE, EXAMPLE_1, EXAMPLE_2,
        COLOR_VISION, PINNED, UNPINNED,
    ];
}

// ------------------------------------------------------------------ hearing what people say
//
// People describe colors in their own words, typed or dictated, in English or Spanish, often
// without accents and with typos. Each idea below (red, "too strong", "worse"...) is a set of
// English words and a set of Spanish ones. Both are always listened for, so a Spanish speaker
// who says "play" or "mute", or an English one who mixes in Spanish, is understood either way.
//
// English is matched on the text in lowercase without accents. Spanish is matched on how it
// sounds: as well as no accents, b and v are one letter, as are s, z and soft c, y and ll, and
// a doubled letter counts once, and h is silent. So "berde", "asul", "amariyo", "rrojo" and
// "se be" are heard as verde, azul, amarillo, rojo and se ve. Spanish patterns are written the
// usual way and turned into how they sound by the same rules.

/// Lowercase, without accents, letters and digits only, one space between words.
fn plain(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push(' ');
    for c in text.chars().flat_map(char::to_lowercase) {
        let c = match c {
            'á' | 'à' | 'â' | 'ä' => 'a',
            'é' | 'è' | 'ê' | 'ë' => 'e',
            'í' | 'ì' | 'î' | 'ï' => 'i',
            'ó' | 'ò' | 'ô' | 'ö' => 'o',
            'ú' | 'ù' | 'û' | 'ü' => 'u',
            'ñ' => 'n',
            '’' | '\'' => '\'',
            c if c.is_alphanumeric() => c,
            _ => ' ',
        };
        if c != ' ' || !out.ends_with(' ') {
            out.push(c);
        }
    }
    if !out.ends_with(' ') {
        out.push(' ');
    }
    out
}

/// A run of letters as it sounds in Spanish (see above). `plain` text in, same text out.
fn sounds(text: &str) -> String {
    let t = text.replace("ll", "y");
    let chars: Vec<char> = t.chars().collect();
    let mut out: Vec<char> = Vec::with_capacity(chars.len());
    for (i, &c) in chars.iter().enumerate() {
        let next = chars.get(i + 1).copied();
        let c = match c {
            'v' => 'b',
            'z' => 's',
            'c' if matches!(next, Some('e' | 'i')) => 's',
            'h' if out.last() != Some(&'c') => continue,
            c => c,
        };
        // A doubled letter counts once ("rr", "tt", "ss"), but never a doubled space or digit.
        if c.is_alphabetic() && out.last() == Some(&c) {
            continue;
        }
        out.push(c);
    }
    out.into_iter().collect()
}

/// A Spanish pattern as it sounds: its runs of letters go through [`sounds`]; regex syntax,
/// escapes like `\b` and spaces are kept as they are.
fn sounds_pattern(pattern: &str) -> String {
    let mut out = String::new();
    let mut run = String::new();
    let mut chars = pattern.chars();
    while let Some(c) = chars.next() {
        if c.is_alphabetic() || c == ' ' {
            run.push(c);
            continue;
        }
        out.push_str(&sounds(&run));
        run.clear();
        out.push(c);
        if c == '\\' {
            if let Some(e) = chars.next() {
                out.push(e);
            }
        }
    }
    out.push_str(&sounds(&run));
    out
}

/// One idea, as people say it in English and in Spanish. Each pattern matches at the start of
/// a word, so "roj" hears rojo, roja and rojizo.
struct Cue {
    en: Regex,
    es: Regex,
}

impl Cue {
    fn new(en: &str, es: &str) -> Cue {
        let build = |p: String| Regex::new(&format!(r"\b(?:{p})")).expect("helper patterns are valid");
        Cue { en: build(en.to_string()), es: build(sounds_pattern(es)) }
    }
}

struct Cues {
    red: Cue,
    green: Cue,
    yellow: Cue,
    brown: Cue,
    orange: Cue,
    blue: Cue,
    /// Blue-green: counts as both.
    teal: Cue,
    purple: Cue,
    grey: Cue,
    dark: Cue,
    solo: Cue,
    mute: Cue,
    solo_and_mute: Cue,
    meter: Cue,
    /// "Too strong": ease everything back.
    less: Cue,
    /// "Still the same", "not enough": go further.
    more: Cue,
    /// "Worse", "go back": put the colors back as they were.
    worse: Cue,
    better: Cue,
    /// "Looks right now", "perfect".
    done: Cue,
    /// "Now I can tell them apart": a colour named in it isn't a problem.
    can_tell: Cue,
    /// "Doesn't look right", "no mejoró": not good news after all.
    negated: Cue,
    /// Words that look like a cue but aren't: "al menos" is "at least".
    not_cues: Cue,
}

fn cues() -> &'static Cues {
    static CUES: OnceLock<Cues> = OnceLock::new();
    CUES.get_or_init(|| Cues {
        red: Cue::new(r"(?:red|reds|redd|reddish|redder)\b|record|clip|rec\b", r"roj|grab|rec\b|clip|satura|pico|picos|pica\b"),
        green: Cue::new(r"gre+n|grean|play", r"verde|verdos|reprodu|play|plei"),
        yellow: Cue::new(r"yel+ow|yello\b|gold|mustard", r"amarill|dorad|mostaza"),
        brown: Cue::new(r"brown|olive|khaki|muddy|beige", r"marron|cafe|castan|pardo|caqui|oliva|ocre|amarronad"),
        orange: Cue::new(r"orange", r"naranj|anaranj"),
        blue: Cue::new(r"blue|blu\b|bleu|navy|cyan|azure", r"azul|celest|cian\b|cyan|marino"),
        teal: Cue::new(r"teal|turquoise|aqua", r"turques|aguamarin"),
        purple: Cue::new(
            r"purple|purpel|purpl|violet|pink|magenta|lilac|lavender|mauve|fuchsia",
            r"morad|violet|lila|purpur|rosa|rosit|fucsia|magenta|malva",
        ),
        grey: Cue::new(r"gr[ae]y|white|silver", r"gris|blanc|platead"),
        dark: Cue::new(r"black|dark|dim\b", r"negr|oscur"),
        solo: Cue::new(r"solo", r"solo"),
        mute: Cue::new(r"mute|muting", r"mut|silen"),
        solo_and_mute: Cue::new(r"s (?:and|&) m\b", r"s y m\b"),
        meter: Cue::new(
            r"meters\b|metering|(?:the|a|level|peak|vu|master|track) meter|meter (?:clip|look|is|turn|go|hit|bar)|levels?\b|(?:level|volume) bars?",
            r"medidor|vumetr|vu metr|nivel|barras? de (?:volumen|nivel)|indicador(?:es)? de nivel",
        ),
        less: Cue::new(
            r"too (?:much|strong|intense|bright|saturated|harsh|bold|vivid|loud|garish|colou?rful)|less\b|weird looking|looks? weird|ugly|natural|harsh|garish|gaudy|tone it|dial it back|ease (?:off|up|it)|softer|subtler|gentler|overdone|overkill|over the top|exaggerated|hurts? my eyes|turn it down|calm it|way too",
            r"demasiado (?:fuerte|intens|brillant|satur|exager|chillon|viv|llamativ|rar|art)|muy (?:fuerte|intens|exager|chillon|satur|viv|llamativ|artificial|brillant)|re (?:fuerte|intens)|(?:se ve|se ven|queda|quedo|luce|lucen|esta|estan|es|son) (?:muy |todo |medio |re |bastante |un poco |demasiado )?(?:rar|fe[oa]|artificial|exager|chillon|horrible)|todo rar|colores? (?:rar|fe[oa])|menos\b|mas (?:suav|natural|tenue|discret|sutil|apagad)|suaviz|suavecit|natural|baj(?:a|ale|ele|alo|elo|ar|e)\b|redu|disminu|te pasaste|se paso|de mas\b|(?:lastima|cansa|molesta|duele|irrita|arde)n? (?:la vista|los ojos)|agresiv|chillon|estridente",
        ),
        more: Cue::new(
            r"still|more\b|not enough|stronger|same|can'?t|cannot|hard|turn it up|crank|increase|push|further|barely|hardly|too (?:weak|subtle|faint|soft|light)|no (?:change|difference)|any difference|intensif|identical|alike|blur|mix up|blend|confus",
            r"todavia|aun\b|sigue|siguen|sigo\b|segui\b|igual|lo mismo|mismo (?:color|tono)|parecid|se parecen|identic|confund|mezcl|no hay manera|no hay forma|(?:sube|subele|subile|subale|aumenta|dale|ponle|pongale|hazlo|hacelo|hagalo|ponlo) (?:un poco )?mas|mas (?:fuerte|intens|contraste|color|correc)|un poco mas|no (?:es )?suficiente|no alcanza|falta|poquito|muy poco|apenas|casi no|no se nota|se nota (?:muy )?poco|no noto|no veo (?:la |ninguna |ningun |nada)|no (?:puedo |logro |alcanzo a |consigo )?(?:distingu|diferenci|separar|ver la diferencia)|no (?:los|las|lo|la|le) (?:distingo|diferencio)|no se (?:distingu|diferenci)|no le hallo|no me doy cuenta|cuesta|dificil|complicad|sub(?:e|ele|ile|ale|ir|elo|ilo)\b|aument|refuerz|reforz|intensific|muy (?:suave|debil|sutil|poco|ligero|tenue)|no sirv|no funciona|no cambi|ningun cambio|sin cambio",
        ),
        worse: Cue::new(
            r"worse|undo|revert|go back|put it back|(?:back|how|the way|like) it was|as it was|change it back|back (?:to|like) (?:before|how|the way)",
            r"peor|empeor|deshaz|deshag|deshacer|deshace\b|como estaba|como lo tenia|(?:vuelv|volv|regres|dej)\w* (?:\w+ )?(?:como antes|atras|a lo de antes|al anterior)|para atras|revert|reviert",
        ),
        better: Cue::new(r"better|improv", r"mejor"),
        done: Cue::new(
            r"perfect|looks? (?:right|good|great|fine|nice|clear)|that'?s (?:it|good|great|right|perfect|fine)|great|awesome|excellent|love it|leave it|keep it|nice|thanks|thank you|good now|all good|works now|much clearer",
            r"perfect|perfet|genial|excelente|buenisim|chever|barbaro|joya|listo|de lujo|ya esta\b|ya quedo|quedo (?:muy |re |super )?(?:bien|chever|genial|perfect|barbaro|joya)|(?:asi|ahora|ya) (?:si )?(?:esta|se ve|se ven|queda|luce) (?:muy |re |super )?bien|se ven? (?:muy )?bien (?:asi|ahora|ya)|asi (?:esta |queda )?(?:bien|perfect)|deja(?:lo|la|los|las)? asi|dejel[oa] asi|me gusta|gracias|ahora si\b|ya si\b",
        ),
        can_tell: Cue::new(
            r"(?:now )?i can (?:now )?(?:tell|see) (?:them|it|the difference|red from green|which)|can tell them apart now|now i can|(?:look|looks|are) (?:different|distinct) now|don'?t look (?:the same|alike)|no longer look|not the same any ?more",
            r"ya (?:los |las |lo |la |le )?(?:distingo|diferencio|separo|veo distint)|ahora si (?:los |las |lo |la )?(?:distingo|diferencio|veo|se distinguen|se ven distint|se ven diferent)|ya (?:se )?(?:distinguen|diferencian)|ya veo la diferencia|ya se (?:nota|ve) la diferencia|ya no (?:se )?(?:ven |son |parecen )?(?:iguales|igual|parecidos|lo mismo)|ya no se (?:confunden|parecen|mezclan)|(?:ahora|ya) (?:se ven|son|los veo|las veo) (?:distint|diferent)",
        ),
        negated: Cue::new(
            r"(?:not|n'?t|no|never) (?:look |looks |seem |seems |really |that |any |much )?(?:right|good|great|better|perfect|fine|clear)",
            r"no (?:se |lo |los |la |las |me |te )?(?:ve|ven|veo|esta|estan|queda|quedo|distingo|distinguen|nota|noto|gusta|mejor|mejoro|mejora|sirve|funciona|ayuda|ayudo)\b|no (?:esta )?(?:bien|mejor)|ni mejor|nada mejor|no hay mejora",
        ),
        not_cues: Cue::new(r"more or less", r"al menos|por lo menos|a menos|mas o menos"),
    })
}

/// A message, ready to be listened to in both languages.
struct Heard {
    plain: String,
    sounds: String,
}

impl Heard {
    fn new(text: &str) -> Heard {
        let plain = plain(text);
        let sounds = sounds(&plain);
        Heard { plain, sounds }
    }

    fn has(&self, cue: &Cue) -> bool {
        cue.en.is_match(&self.plain) || cue.es.is_match(&self.sounds)
    }

    /// The message with every match of `cue` taken out.
    fn without(&self, cue: &Cue) -> Heard {
        Heard { plain: cue.en.replace_all(&self.plain, " ").into(), sounds: cue.es.replace_all(&self.sounds, " ").into() }
    }
}

// ------------------------------------------------------------------ answering

/// Rule-based helper for when Claude isn't available, answering in English.
pub fn offline_reply(text: &str, p: &Profile, state: &mut HelperState) -> Suggestion {
    offline_reply_in(text, p, state, Lang::En)
}

/// Rule-based helper for when Claude isn't available. It understands the common ways people
/// describe red-green and blue-yellow confusion, named controls, "too strong", "not enough",
/// "worse" and "that's right", in English and Spanish, and answers in `lang`.
pub fn offline_reply_in(text: &str, p: &Profile, state: &mut HelperState, lang: Lang) -> Suggestion {
    let c = cues();
    let all = Heard::new(text);
    let heard = all.without(&c.not_cues);
    let can_tell = heard.has(&c.can_tell);
    // "Ya no se ven iguales": "iguales" there is good news, not "still the same".
    let rest = heard.without(&c.can_tell);
    let teal = heard.has(&c.teal);
    let red = heard.has(&c.red);
    let green = heard.has(&c.green) || teal;
    let yellow = heard.has(&c.yellow);
    let brown = heard.has(&c.brown);
    let orange = heard.has(&c.orange);
    let blue = heard.has(&c.blue) || teal;
    let purple = heard.has(&c.purple);
    let grey = heard.has(&c.grey);
    let less = rest.has(&c.less);
    let more = rest.has(&c.more);
    let worse = rest.has(&c.worse);
    let pleased = (rest.has(&c.better) || rest.has(&c.done)) && !rest.has(&c.negated);
    let st = &p.settings;
    let mut r = Suggestion::default();
    let ch = |r: &mut Suggestion, k: &str, v: f64| {
        r.changes.insert(k.to_string(), v);
    };
    let say = |r: &mut Suggestion, reply: &str, question: &str| {
        r.reply = t(lang, reply);
        r.question = if question.is_empty() { String::new() } else { t(lang, question) };
    };

    if worse && !less {
        if let Some((before, after)) = state.undo.take() {
            if &after == p {
                state.last = None;
                r.kind = "undo";
                for (k, _, _) in RANGES {
                    ch(&mut r, k, before.settings.get(k).unwrap_or(0.0));
                }
                r.cvd = Some(before.settings.cvd);
                for (id, a) in &before.anchors {
                    if role(id).is_some() && p.anchors.get(id) != Some(a) {
                        r.anchors.insert(id.clone(), a.to.clone());
                    }
                }
                r.remove_anchors = p.anchors.keys().filter(|id| !before.anchors.contains_key(*id)).cloned().collect();
                say(&mut r, said::UNDONE, said::TRY_ANOTHER);
                return r;
            }
        }
    }
    if less || worse {
        r.kind = "less";
        for k in ["daltonize", "rgSplit", "bySplit", "redShift", "greenShift", "yellowShift", "blueShift"] {
            ch(&mut r, k, st.get(k).unwrap_or(0.0) * 0.6);
        }
        ch(&mut r, "saturation", 1.0 + (st.saturation - 1.0) * 0.6);
        say(&mut r, said::EASED, said::STILL_TELL);
        return remember(r, p, state);
    }
    if can_tell && !more {
        r.kind = "keep";
        say(&mut r, said::DONE, "");
        return r;
    }
    if (heard.has(&c.solo) && heard.has(&c.mute)) || heard.has(&c.solo_and_mute) {
        r.kind = "soloMute";
        r.anchors.insert("solo".into(), safe::YELLOW.into());
        r.anchors.insert("mute".into(), safe::BLUE.into());
        say(&mut r, said::SOLO_MUTE, said::SOLO_MUTE_Q);
        return remember(r, p, state);
    }
    if heard.has(&c.meter) {
        r.kind = "meters";
        r.anchors.insert("meterLow".into(), safe::SKY.into());
        r.anchors.insert("meterMid".into(), safe::YELLOW.into());
        r.anchors.insert("meterClip".into(), safe::VERMILLION.into());
        ch(&mut r, "rgSplit", st.rg_split + 0.2);
        say(&mut r, said::METERS, said::METERS_Q);
        return remember(r, p, state);
    }
    if red && heard.has(&c.dark) {
        state.last = Some("protan");
        r.kind = "protan";
        r.cvd = Some(CvdType::Protan);
        ch(&mut r, "severity", st.severity.max(0.8));
        ch(&mut r, "daltonize", st.daltonize.max(0.5));
        ch(&mut r, "rgSplit", st.rg_split + 0.35);
        ch(&mut r, "redShift", st.red_shift - 15.0);
        say(&mut r, said::PROTAN, said::PROTAN_Q);
        return remember(r, p, state);
    }
    let red_green = (red && green) || ((red || green) && (yellow || brown || orange) && !blue);
    let blue_yellow = (blue && (green || purple)) || (yellow && (purple || grey));
    let further = more && !red_green && !blue_yellow;
    if red_green || (further && state.last == Some("rg")) {
        let step = if more && state.last == Some("rg") { 1.5 } else { 1.0 };
        state.last = Some("rg");
        r.kind = "rg";
        if st.cvd == CvdType::Tritan {
            r.cvd = Some(CvdType::Deutan);
        }
        ch(&mut r, "daltonize", st.daltonize.max(0.5) * if step > 1.0 { 1.25 } else { 1.0 });
        ch(&mut r, "redShift", st.red_shift - 20.0 * step);
        ch(&mut r, "greenShift", st.green_shift + 22.0 * step);
        ch(&mut r, "rgSplit", st.rg_split + 0.15 * step);
        say(&mut r, if step > 1.0 { said::RG_FURTHER } else { said::RG }, said::RG_Q);
        return remember(r, p, state);
    }
    if blue_yellow || (further && state.last == Some("by")) {
        let again = more && state.last == Some("by");
        state.last = Some("by");
        r.kind = "by";
        r.cvd = Some(CvdType::Tritan);
        ch(&mut r, "severity", st.severity.max(0.7));
        ch(&mut r, "daltonize", st.daltonize.max(0.5));
        ch(&mut r, "bySplit", st.by_split + 0.3);
        ch(&mut r, "blueShift", st.blue_shift + 15.0);
        ch(&mut r, "greenShift", st.green_shift - 12.0);
        say(&mut r, if again { said::BY_FURTHER } else { said::BY }, said::BY_Q);
        return remember(r, p, state);
    }
    if pleased && !more {
        r.kind = "keep";
        if rest.has(&c.done) {
            say(&mut r, said::DONE, "");
        } else {
            say(&mut r, said::BETTER, said::ANYTHING_ELSE);
        }
        return r;
    }
    if more {
        r.kind = "more";
        ch(&mut r, "daltonize", st.daltonize + 0.2);
        ch(&mut r, "saturation", st.saturation + 0.15);
        say(&mut r, said::MORE, said::MORE_Q);
        return remember(r, p, state);
    }
    r.kind = "ask";
    r.reply = tf(lang, said::NOT_SURE, &[("example1", &quoted(lang, said::EXAMPLE_1)), ("example2", &quoted(lang, said::EXAMPLE_2))]);
    r
}

/// Words the person could say, in quotes as the language writes them.
fn quoted(lang: Lang, en: &str) -> String {
    match lang {
        Lang::En => format!("\"{en}\""),
        Lang::Es => format!("«{}»", t(lang, en)),
    }
}

/// Keeps the colors before and after a change, so "that's worse" can undo it.
fn remember(r: Suggestion, p: &Profile, state: &mut HelperState) -> Suggestion {
    let mut after = p.clone();
    r.apply_to(&mut after);
    state.undo = Some((p.clone(), after));
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    fn turn(text: &str, p: &mut Profile, st: &mut HelperState, lang: Lang) -> Suggestion {
        let s = offline_reply_in(text, p, st, lang);
        s.apply_to(p);
        s
    }

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
    fn spanish_is_understood_and_answered_in_spanish() {
        let mut p = Profile::default();
        let mut st = HelperState::default();
        let s = turn("lo que debería ser rojo lo veo como un verde o amarillo raro", &mut p, &mut st, Lang::Es);
        assert_eq!(s.kind, "rg");
        assert!(p.settings.red_shift < 0.0 && p.settings.green_shift > 0.0);
        assert!(s.reply.starts_with("Parece daltonismo rojo-verde"), "{}", s.reply);
        assert!(s.question.contains('¿') && s.question.ends_with('?'), "{}", s.question);
        // Dictated, without accents, it still goes further in the same direction.
        let before = p.settings.red_shift;
        let s = turn("todavia se ven iguales", &mut p, &mut st, Lang::Es);
        assert!(p.settings.red_shift < before - 25.0, "{}", s.reply);
        // The list of what changed is in Spanish too.
        let mut q = Profile::default();
        let done = offline_reply_in("no distingo el solo del mute", &q, &mut HelperState::default(), Lang::Es).apply_in(&mut q, Lang::Es);
        assert!(done.iter().any(|d| d.starts_with("Fijado")), "{done:?}");
    }

    #[test]
    fn worse_puts_back_the_last_change_and_only_that() {
        let mut p = Profile::default();
        let start = p.clone();
        let mut st = HelperState::default();
        turn("no distingo el solo del mute", &mut p, &mut st, Lang::Es);
        let pinned = p.clone();
        turn("el rojo y el verde se ven iguales", &mut p, &mut st, Lang::Es);
        let s = turn("se ve peor", &mut p, &mut st, Lang::Es);
        assert_eq!(s.kind, "undo");
        assert_eq!(p, pinned, "back to before the red-green change, pins kept");
        assert_ne!(p, start);
        // Nothing left to undo: "worse" again eases back instead of flipping back and forth.
        assert_eq!(turn("worse", &mut p, &mut st, Lang::En).kind, "less");
        // A change made since (a fader, Claude) isn't thrown away: it eases back instead.
        turn("blue and green look the same", &mut p, &mut st, Lang::En);
        p.settings.contrast = 1.3;
        assert_eq!(turn("that's worse", &mut p, &mut st, Lang::En).kind, "less");
    }

    #[test]
    fn good_news_changes_nothing() {
        let mut p = Profile::default();
        let mut st = HelperState::default();
        turn("red and green look the same", &mut p, &mut st, Lang::En);
        for (text, lang) in [("much better, thanks", Lang::En), ("ya distingo el rojo del verde", Lang::Es), ("ya no se ven iguales", Lang::Es)] {
            let before = p.clone();
            let s = turn(text, &mut p, &mut st, lang);
            assert_eq!((s.kind, &p), ("keep", &before), "{text}");
        }
        // Not good news after all.
        assert_ne!(turn("todavía no se ve bien", &mut p, &mut st, Lang::Es).kind, "keep");
    }

    #[test]
    fn spanish_sounds_the_same_however_it_is_spelled() {
        assert_eq!(sounds(&plain("Verde, AZUL y amarrillo")), sounds(&plain("berde asul y amariyo")));
        assert_eq!(sounds(&plain("se ve")), sounds(&plain("se be")));
        assert_eq!(sounds(&plain("silencio")), " silensio ");
        assert_eq!(sounds_pattern(r"verde|\broj|barras? de (?:volumen|nivel)"), r"berde|\broj|baras? de (?:bolumen|nibel)");
        // "Solo" alone is an adverb in Spanish ("solo veo verde"): it takes Mute too.
        let s = offline_reply_in("solo veo bien el azul, el rojo y el verde no los distingo", &Profile::default(), &mut HelperState::default(), Lang::Es);
        assert_eq!(s.kind, "rg");
    }

    #[test]
    fn every_sentence_has_spanish() {
        let missing: Vec<_> = said::ALL.iter().filter(|s| !crate::lang::spanish().contains_key(**s)).collect();
        assert!(missing.is_empty(), "no Spanish for {missing:?}");
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

    #[test]
    fn reads_claude_in_spanish() {
        let text = "{\"reply\":\"Fijé Solo en amarillo y Silenciar en azul, así se distinguen también por el brillo. «Ñandú» ✓\",\"changes\":{},\"anchors\":{\"solo\":\"#f0e442\"},\"question\":\"¿Ahora ves distintos los botones S y M?\"}";
        let s = Suggestion::from_model_text(text).unwrap();
        assert!(s.reply.ends_with("«Ñandú» ✓"));
        assert_eq!(s.question, "¿Ahora ves distintos los botones S y M?");
        // Long replies are cut at a character, never inside one.
        let long = format!("{{\"reply\":\"{}\"}}", "ñ".repeat(900));
        assert_eq!(Suggestion::from_model_text(&long).unwrap().reply.chars().count(), 800);
    }
}
