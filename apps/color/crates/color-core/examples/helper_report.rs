//! How well the offline helper understands people describing what they see, in English and
//! Spanish: the share of descriptions where it does what it should (tests/descriptions/*.tsv),
//! by what it should do and by who is talking, and each miss on the seen sets.
//! Run with: cargo run -p color-core --example helper_report
//! The held-out and blind sets' misses stay hidden, so the rules aren't written against them;
//! add `--held-misses` to see them once a change is done.

#[path = "../tests/descriptions/harness.rs"]
mod harness;

fn main() {
    let held_misses = std::env::args().any(|a| a == "--held-misses");
    let scores: Vec<_> = harness::SETS.iter().map(|&(name, lang)| (name, harness::score(name, lang))).collect();
    println!("{:<10} {:>9} {:>7}", "set", "right", "share");
    for (name, sc) in &scores {
        println!("{name:<10} {:>4}/{:<4} {:>6.1}%", sc.right, sc.total, sc.percent());
    }
    println!("\nBy what it should do (right/total in each set):");
    let mut kinds: Vec<&String> = scores.iter().flat_map(|(_, sc)| sc.by_expect.keys()).collect();
    kinds.sort();
    kinds.dedup();
    print!("{:<10}", "");
    for (name, _) in &scores {
        print!(" {name:>9}");
    }
    println!();
    for k in kinds {
        print!("{k:<10}");
        for (_, sc) in &scores {
            let (r, t) = sc.by_expect.get(k).copied().unwrap_or((0, 0));
            print!(" {:>9}", format!("{r}/{t}"));
        }
        println!();
    }
    for (name, sc) in &scores {
        println!("\n{name}, by who is talking:");
        for (who, (r, t)) in &sc.by_who {
            println!("   {who:<10} {r}/{t}");
        }
    }
    for (name, sc) in &scores {
        if !name.ends_with("seen") && !held_misses {
            continue;
        }
        if !sc.misses.is_empty() {
            println!("\n{name}, missed:");
        }
        for (text, expect, got) in &sc.misses {
            println!("   [{expect}] {text}\n        -> {got}");
        }
    }
}
