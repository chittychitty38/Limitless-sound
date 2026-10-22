//! Prints what automatic tuning chooses for each kind of color vision.
//! Run with: cargo run --release -p color-core --example tune_report
//! Add `--json` to print every result as JSON instead (the app's auto_tune_profile answer).
use color_core::tune::auto_tune;
use color_core::CvdType;

fn main() {
    if std::env::args().any(|a| a == "--json") {
        let mut all = serde_json::Map::new();
        for cvd in CvdType::ALL {
            for sev in [0.2, 0.4, 0.6, 0.7, 0.8, 1.0] {
                all.insert(format!("{}-{sev}", serde_json::to_value(cvd).unwrap().as_str().unwrap()), serde_json::to_value(auto_tune(cvd, sev)).unwrap());
            }
        }
        println!("{}", serde_json::Value::Object(all));
        return;
    }
    for cvd in CvdType::ALL {
        for sev in [0.4, 0.7, 1.0] {
            let r = auto_tune(cvd, sev);
            let s = &r.profile.settings;
            println!(
                "{cvd:?} {sev}: daltonize {:.2} rg {:.2} by {:.2} red {:.0} yellow {:.0} green {:.0} blue {:.0} sat {:.2} pins {:?}",
                s.daltonize, s.rg_split, s.by_split, s.red_shift, s.yellow_shift, s.green_shift, s.blue_shift, s.saturation, r.pinned
            );
            for p in &r.pairs {
                println!("   {:<28} {:.3} -> {:.3}", p.label, p.before, p.after);
            }
        }
    }
}
