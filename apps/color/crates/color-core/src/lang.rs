//! Limitless Color in the suite's language: English or Spanish.
//!
//! English is written in the code. The Spanish is the tuner window's own table
//! (`app/ui/index.html`, the `strings-es` script, English text → Spanish), the same one the
//! window, the menus and the app's messages read, so every word has one Spanish in one place.
//! Text with no Spanish stays English.

use std::collections::HashMap;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};

/// A language Color speaks: a lowercase BCP 47 primary tag, as the suite's `language` setting.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Lang {
    #[default]
    En,
    Es,
}

impl Lang {
    pub const ALL: [Lang; 2] = [Lang::En, Lang::Es];

    pub fn code(self) -> &'static str {
        match self {
            Lang::En => "en",
            Lang::Es => "es",
        }
    }

    /// `"es"`, `"es-MX"`, `"es_ES.UTF-8"` → Spanish; `None` when Color doesn't have the language.
    pub fn from_tag(value: &str) -> Option<Lang> {
        let primary = value.trim().replace('_', "-");
        let primary = primary.split(['-', '.']).next().unwrap_or("").to_lowercase();
        match primary.as_str() {
            "en" => Some(Lang::En),
            "es" => Some(Lang::Es),
            _ => None,
        }
    }

    /// The first of the computer's languages (most preferred first) that Color has, else English.
    pub fn first_of<S: AsRef<str>>(found: &[S]) -> Lang {
        found.iter().find_map(|v| Lang::from_tag(v.as_ref())).unwrap_or_default()
    }

    /// The language's name in English, for Claude's instructions.
    pub fn english_name(self) -> &'static str {
        match self {
            Lang::En => "English",
            Lang::Es => "Spanish",
        }
    }
}

/// The tuner window, which carries the Spanish.
const PAGE: &str = include_str!("../../../app/ui/index.html");
const TABLE: &str = r#"<script type="application/json" id="strings-es">"#;

/// English → Spanish, from a page's `strings-es` table. Empty when the page has none.
pub fn parse_table(page: &str) -> HashMap<String, String> {
    let Some(start) = page.find(TABLE).map(|i| i + TABLE.len()) else { return HashMap::new() };
    let end = page[start..].find("</script>").map_or(page.len(), |i| start + i);
    serde_json::from_str(&page[start..end]).expect("the strings-es table in app/ui/index.html is valid JSON")
}

/// Color's Spanish, English text → Spanish.
pub fn spanish() -> &'static HashMap<String, String> {
    static ES: OnceLock<HashMap<String, String>> = OnceLock::new();
    ES.get_or_init(|| parse_table(PAGE))
}

/// `en` in `lang`: the Spanish for it, or the English when there is none.
pub fn t(lang: Lang, en: &str) -> String {
    match lang {
        Lang::En => en.to_string(),
        Lang::Es => spanish().get(en).cloned().unwrap_or_else(|| en.to_string()),
    }
}

/// [`t`], then each `{name}` in it replaced by its value.
pub fn tf(lang: Lang, en: &str, vars: &[(&str, &str)]) -> String {
    let mut out = t(lang, en);
    for (name, value) in vars {
        out = out.replace(&format!("{{{name}}}"), value);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_language_is_its_primary_tag_and_only_one_color_has() {
        assert_eq!(Lang::from_tag("es"), Some(Lang::Es));
        assert_eq!(Lang::from_tag("es-MX"), Some(Lang::Es));
        assert_eq!(Lang::from_tag("es_ES.UTF-8"), Some(Lang::Es));
        assert_eq!(Lang::from_tag(" EN-us "), Some(Lang::En));
        assert_eq!(Lang::from_tag("fr-FR"), None);
        assert_eq!(Lang::from_tag(""), None);
    }

    #[test]
    fn the_computers_language_is_the_first_one_color_has() {
        assert_eq!(Lang::first_of(&["es-MX", "en-US"]), Lang::Es);
        assert_eq!(Lang::first_of(&["fr-FR", "es-ES"]), Lang::Es);
        assert_eq!(Lang::first_of(&["en-GB", "es-ES"]), Lang::En);
        assert_eq!(Lang::first_of(&["fr-FR", "de-DE"]), Lang::En);
        assert_eq!(Lang::first_of::<&str>(&[]), Lang::En);
    }

    #[test]
    fn the_suite_names_languages_the_same_way() {
        assert_eq!(serde_json::to_value(Lang::Es).unwrap(), "es");
        assert_eq!(serde_json::from_value::<Lang>("en".into()).unwrap(), Lang::En);
        assert_eq!(Lang::Es.code(), "es");
    }

    #[test]
    fn a_table_reads_from_its_page() {
        let page = r#"<p>Hi</p><script type="application/json" id="strings-es">{"Hi": "Hola", "Open {name}": "Abrir {name}"}</script>"#;
        let es = parse_table(page);
        assert_eq!(es["Hi"], "Hola");
        assert!(parse_table("<p>no table</p>").is_empty());
    }

    #[test]
    fn text_without_spanish_stays_english() {
        assert_eq!(t(Lang::Es, "A sentence nobody translated"), "A sentence nobody translated");
        assert_eq!(tf(Lang::En, "Open {name}", &[("name", "Limitless Color")]), "Open Limitless Color");
    }
}
