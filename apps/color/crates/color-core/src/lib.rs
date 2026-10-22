//! Shared color engine for Limitless Color: simulation of color vision
//! differences, the correction a person tunes, 3D lookup tables for the screen
//! filter, a matrix fit for the Windows color filter, and the assistant's
//! offline rules and prompt.

pub mod color;
pub mod helper;
pub mod lut;
pub mod matrix;
pub mod profile;
pub mod prompt;
pub mod tune;
#[cfg(test)]
mod testdata;

pub use color::CvdType;
pub use profile::{Anchor, Profile, Settings, Transform};
