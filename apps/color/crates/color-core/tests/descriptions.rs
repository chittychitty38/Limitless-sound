//! The offline helper on people's own descriptions of what they see, in English and Spanish
//! (tests/descriptions/*.tsv). A Spanish speaker gets help as good as an English speaker's.
//! cargo run -p color-core --example helper_report prints the numbers and what it got wrong.

#[path = "descriptions/harness.rs"]
mod harness;

use color_core::lang::{self, Lang};

/// The share each set must keep, a little under what it scored when the floors were set.
const FLOORS: [(&str, f64); 4] = [("en-seen", 97.0), ("en-held", 95.0), ("es-seen", 97.0), ("es-held", 95.0)];

#[test]
fn the_helper_understands_people_in_both_languages() {
    let mut report = vec![];
    let mut low = vec![];
    for (name, lang) in harness::SETS {
        let sc = harness::score(name, lang);
        report.push(format!("{name} {:.1}%", sc.percent()));
        let floor = FLOORS.iter().find(|f| f.0 == name).unwrap().1;
        if sc.percent() < floor {
            low.push(format!("{name}: {:.1}% (floor {floor}%), missed {:?}", sc.percent(), sc.misses));
        }
    }
    println!("{}", report.join(", "));
    assert!(low.is_empty(), "{}", low.join("\n"));
}

#[test]
fn spanish_answers_are_in_spanish() {
    // Every answer the helper gave a Spanish description is the Spanish of an English sentence.
    let spanish: std::collections::HashSet<&String> = lang::spanish().values().collect();
    for name in ["es-seen", "es-held"] {
        for case in harness::load(name) {
            let (_, s) = harness::run(&case, Lang::Es);
            assert!(!s.reply.is_empty(), "{}", case.text);
            for said in [&s.reply, &s.question] {
                let plain = !said.is_empty() && !said.contains('«');
                assert!(!plain || spanish.contains(said), "not Spanish: {said} (for {})", case.text);
            }
        }
    }
}
