//! The screen filter: applies a profile to everything on screen.
//!
//! - macOS: a helper captures each display and redraws it through the profile's
//!   lookup table on the GPU (exact match to the tuner).
//! - Windows: the built-in full-screen color matrix (Magnification API), fitted
//!   to the profile. Zero lag and nearly zero cost, but a matrix can only
//!   approximate pinned colors and hue moves.

use color_core::Profile;
use tauri::AppHandle;

#[cfg(target_os = "macos")]
pub mod macos;
#[cfg(windows)]
pub mod windows;

pub trait ScreenFilter: Send {
    /// "overlay", "matrix" or "none"
    fn kind(&self) -> &'static str;
    /// Shows the profile on screen (or removes the filter when `on` is false).
    /// Returns a short note for the person, such as how close the match is.
    fn apply(&mut self, profile: &Profile, on: bool) -> Result<String, String>;
    /// Starts over from scratch on the next `apply`, for example after a permission was granted.
    fn restart(&mut self) {}
}

struct Unsupported;

impl ScreenFilter for Unsupported {
    fn kind(&self) -> &'static str {
        "none"
    }
    fn apply(&mut self, _: &Profile, on: bool) -> Result<String, String> {
        if on {
            Err("Whole-screen colors work on Mac and Windows. On this computer the tuner preview still works.".into())
        } else {
            Ok(String::new())
        }
    }
}

pub fn create(app: &AppHandle) -> Box<dyn ScreenFilter> {
    #[cfg(target_os = "macos")]
    {
        return Box::new(macos::Overlay::new(app.clone()));
    }
    #[cfg(windows)]
    {
        let _ = app;
        return Box::new(windows::MatrixFilter::new());
    }
    #[allow(unreachable_code)]
    {
        let _ = app;
        Box::new(Unsupported)
    }
}
