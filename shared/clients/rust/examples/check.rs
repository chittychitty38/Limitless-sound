//! Used by shared/hub/tests/test_clients.py: a Color-like app over the real hub.
use limitless_link::{Action, Link};
use std::{thread, time::Duration};

fn main() {
    let link = Link::new("color", "Limitless Color", "test",
        vec![Action::new("on", "Screen colors on"), Action::new("off", "Screen colors off")]);
    let l2 = link.clone();
    link.state("ready", true.into()); // before connecting: the hub still hears it
    link.start(
        move |action, _args, _src| {
            l2.state("filter", (action == "on").into());
            (true, format!("rust did {action}"))
        },
        |name, _value, _src| println!("EVENT {name}"),
    );
    for _ in 0..50 {
        if link.connected() { break; }
        thread::sleep(Duration::from_millis(50));
    }
    println!("CONNECTED {}", link.connected());
    link.invoke("zoom.in", serde_json::json!({}));
    thread::sleep(Duration::from_millis(2500));
}
