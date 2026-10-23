//! The offline helper on people's own descriptions of what they see, in English and Spanish.
//! cargo run -p color-core --example helper_report prints the numbers and what it got wrong.

#[path = "descriptions/harness.rs"]
mod harness;

#[test]
fn baseline_numbers() {
    for (name, lang) in harness::SETS {
        let sc = harness::score(name, lang);
        println!("{name}: {}/{} = {:.1}%", sc.right, sc.total, sc.percent());
        for (k, (r, t)) in &sc.by_expect {
            println!("   {k:<10} {r}/{t}");
        }
    }
}
