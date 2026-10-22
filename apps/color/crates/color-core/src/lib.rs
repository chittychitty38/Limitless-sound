//! Shared color engine for Limitless Color: simulation of color vision
//! differences, the correction a person tunes, 3D lookup tables for the screen
//! filter, a matrix fit for the Windows color filter, the assistant's offline
//! rules and prompt, and the suite's shared settings for the tuner window.

pub mod color;
pub mod helper;
pub mod lut;
pub mod matrix;
pub mod prefs;
pub mod profile;
pub mod prompt;
pub mod tune;
#[cfg(test)]
mod testdata;

pub use color::CvdType;
pub use prefs::WindowPrefs;
pub use profile::{Anchor, Profile, Settings, Transform};
