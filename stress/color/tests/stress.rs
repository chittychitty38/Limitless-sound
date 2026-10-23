//! Limitless Color's engine with every slider at every extreme, hostile profile files,
//! a long conversation with the offline helper, and the speed of rebuilding the screen
//! filter while a slider is dragged.

use color_core::lut::{Lut3D, DEFAULT_SIZE};
use color_core::profile::RANGES;
use color_core::{helper, matrix, Anchor, CvdType, Profile};
use std::time::Instant;

/// A small, dependency-free random number generator so runs are repeatable.
struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
    fn pick<'a, T>(&mut self, items: &'a [T]) -> &'a T {
        &items[(self.next() % items.len() as u64) as usize]
    }
    fn hex(&mut self) -> String {
        format!("#{:06x}", self.next() & 0xff_ffff)
    }
}

fn random_profile(rng: &mut Rng) -> Profile {
    let mut p = Profile::default();
    p.settings.cvd = *rng.pick(&CvdType::ALL);
    for (key, lo, hi) in RANGES {
        // A third of the time, park the slider at an end: that's where math breaks.
        let v = match rng.next() % 3 {
            0 => *rng.pick(&[lo, hi]),
            _ => lo + (hi - lo) * rng.unit(),
        };
        p.settings.set(key, v);
    }
    for i in 0..(rng.next() % 6) {
        p.anchors.insert(format!("a{i}"), Anchor { from: rng.hex(), to: rng.hex(), label: String::new() });
    }
    p
}

fn assert_sane(lut: &Lut3D, what: &str) {
    for (i, c) in lut.data.iter().enumerate() {
        for v in c {
            assert!(v.is_finite() && (0.0..=1.0).contains(v), "{what}: entry {i} is {c:?}");
        }
    }
}

#[test]
fn every_slider_at_every_extreme_gives_a_sane_screen() {
    let mut rng = Rng(0x5eed);
    for n in 0..400 {
        let p = random_profile(&mut rng);
        let lut = Lut3D::from_profile(&p, 17);
        assert_sane(&lut, &format!("profile {n}: {}", p.to_json()));
        let m = matrix::fit(&p);
        let effect = matrix::to_mag_color_effect(&m);
        assert!(effect.iter().all(|v| v.is_finite()), "Windows matrix not finite for {}", p.to_json());
        assert!(matrix::fit_error(&p, &m).is_finite());
    }
}

#[test]
fn hostile_profile_files_never_crash_the_app() {
    let cases = [
        r##"{}"##,
        r##"{"S": {}}"##,
        r##"{"S": {"severity": 1e308, "contrast": -1e308, "saturation": 0}}"##,
        r##"{"S": {"type": "tritan", "redShift": 99999, "focus": 0}}"##,
        r##"{"S": {"severity": "lots"}}"##,
        r##"{"S": {"type": "martian"}}"##,
        r##"{"S": {}, "anchors": {"x": {"from": "not a color", "to": "#zzzzzz"}}}"##,
        r##"{"S": {}, "anchors": {"x": {"from": "#000000", "to": "#000000"}, "y": {"from": "#000000", "to": "#ffffff"}}}"##,
        r##"[1,2,3]"##,
        "",
        "{\"S\": {\"severity\": 0.5",
    ];
    for text in cases {
        if let Ok(p) = Profile::from_json(text) {
            assert_sane(&Lut3D::from_profile(&p, 9), text);
            for (key, lo, hi) in RANGES {
                let v = p.settings.get(key).unwrap();
                assert!(v >= lo && v <= hi, "{key} = {v} slipped past its range from {text}");
            }
        }
    }
}

#[test]
fn a_long_conversation_with_the_offline_helper_stays_in_range() {
    let lines = [
        "red looks like a weird green or yellow", "still the same", "too much", "the play button looks brown",
        "record and mute look the same", "blue and purple are mixed up", "it's too bright", "everything is washed out",
        "better", "worse", "still", "more", "less", "reset", "solo looks grey", "meters are hard to read",
        "", "🎸🎸🎸", "the the the the the the", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        // The same conversation in Spanish, typed and dictated.
        "lo rojo lo veo como un verde raro", "sigue igual", "demasiado fuerte", "se ve peor", "volvé a como estaba",
        "mejor", "ya no se ven iguales", "todavia no distingo grabar de play", "el azul y el morado se confunden",
        "no distingo el solo del mute", "los medidores se ven de un solo color", "bájale tantito", "súbele", "ñññ ¿¡«»",
    ];
    let mut rng = Rng(42);
    let mut p = Profile::default();
    let mut state = helper::HelperState::default();
    for _ in 0..5000 {
        let line = *rng.pick(&lines);
        let lang = *rng.pick(&color_core::Lang::ALL);
        let s = helper::offline_reply_in(line, &p, &mut state, lang);
        s.apply_to(&mut p);
        for (key, lo, hi) in RANGES {
            let v = p.settings.get(key).unwrap();
            assert!(v.is_finite() && v >= lo - 1e-9 && v <= hi + 1e-9, "{key} drifted to {v} after “{line}”");
        }
    }
    assert_sane(&Lut3D::from_profile(&p, 9), "after the conversation");
    let long = "red ".repeat(20000);
    helper::offline_reply(&long, &p, &mut state);
}

#[test]
fn rebuilding_the_screen_filter_keeps_up_with_a_dragged_slider() {
    // Every slider move rebuilds the full lookup table for the Mac overlay. At 60 moves a second
    // anything over ~16 ms per table makes the screen lag behind the hand.
    let mut rng = Rng(7);
    let profiles: Vec<Profile> = (0..30).map(|_| random_profile(&mut rng)).collect();
    let t0 = Instant::now();
    for p in &profiles {
        let lut = Lut3D::from_profile(p, DEFAULT_SIZE);
        std::hint::black_box(lut.to_rgba8());
    }
    let per = t0.elapsed().as_secs_f64() / profiles.len() as f64;
    println!("lookup table ({DEFAULT_SIZE}³) rebuilt in {:.1} ms", per * 1000.0);
    assert!(per < 0.25, "rebuilding the screen filter takes {:.0} ms", per * 1000.0);
}
