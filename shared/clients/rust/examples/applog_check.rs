//! Exercises applog.rs for the hub's tests (shared/hub/tests/test_applog.py):
//!   applog_check stamp <unix ms>   prints that time as the log writes it
//!   applog_check busy              writes 7000 long lines, to show the log stays small
//!   applog_check                   writes a few lines, then panics in a thread and in main

#[path = "../src/applog.rs"]
mod applog;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("stamp") => println!("{}", applog::stamp_at(args[1].parse().unwrap())),
        Some("busy") => {
            applog::start("Busy", "");
            for i in 0..7000 {
                applog::info(&format!("line {i} {}", "x".repeat(200)));
            }
        }
        _ => {
            println!("{:?}", applog::start("Test App", "1.2.3"));
            applog::info("ready");
            applog::warn("no shortcut");
            applog::error("filter failed");
            let _ = std::thread::Builder::new()
                .name("worker".into())
                .spawn(|| panic!("worker gave up"))
                .unwrap()
                .join();
            panic!("nobody caught me");
        }
    }
}
