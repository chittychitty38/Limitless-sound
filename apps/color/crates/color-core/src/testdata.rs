//! Reference values produced by the tuner page's JavaScript, so the screen
//! filter and the preview never drift apart.

/// deutan 0.8, daltonize 0.5, rgSplit 0.15, redShift -20, greenShift 22, applied to
/// record, play, solo and mute.
pub const JS_EXPECTED: [&str; 4] = ["#ec5d97", "#00b462", "#efd03a", "#28a2ce"];
