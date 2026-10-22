//! Windows: the full-screen color matrix built into Windows (Magnification API).
//! Every app, game and plugin window is covered, with no capture and no lag.

use std::sync::mpsc::{channel, Sender};

use color_core::matrix::{fit, fit_error, to_mag_color_effect, IDENTITY};
use color_core::Profile;
use windows::Win32::UI::Input::KeyboardAndMouse::{
    SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP, VIRTUAL_KEY, VK_H, VK_LWIN,
};
use windows::Win32::UI::Magnification::{MagInitialize, MagSetFullscreenColorEffect, MagUninitialize, MAGCOLOREFFECT};

pub struct MatrixFilter {
    tx: Sender<[f32; 25]>,
}

impl MatrixFilter {
    pub fn new() -> MatrixFilter {
        let (tx, rx) = channel::<[f32; 25]>();
        // The Magnification API wants every call on the thread that initialized it.
        std::thread::spawn(move || unsafe {
            if !MagInitialize().as_bool() {
                return;
            }
            while let Ok(m) = rx.recv() {
                let effect = MAGCOLOREFFECT { transform: m };
                let _ = MagSetFullscreenColorEffect(&effect);
            }
            let effect = MAGCOLOREFFECT { transform: to_mag_color_effect(&IDENTITY) };
            let _ = MagSetFullscreenColorEffect(&effect);
            let _ = MagUninitialize();
        });
        MatrixFilter { tx }
    }
}

impl super::ScreenFilter for MatrixFilter {
    fn kind(&self) -> &'static str {
        "matrix"
    }

    fn apply(&mut self, profile: &Profile, on: bool) -> Result<String, String> {
        let m = if on { fit(profile) } else { IDENTITY };
        self.tx.send(to_mag_color_effect(&m)).map_err(|_| "The Windows color filter isn't available.".to_string())?;
        if !on {
            return Ok(String::new());
        }
        let err = fit_error(profile, &m);
        Ok(if err < 6.0 {
            "Matches the tuner closely.".into()
        } else if err < 15.0 {
            "Close to the tuner. Pinned colors may look a little different on screen.".into()
        } else {
            "Rough match: Windows' built-in filter can't follow every pinned color or hue move. Try fewer pins or smaller moves.".into()
        })
    }
}

impl Drop for MatrixFilter {
    fn drop(&mut self) {
        let _ = self.tx.send(to_mag_color_effect(&IDENTITY));
    }
}

/// Presses Windows+H, which opens Windows voice typing in the focused text box.
pub fn press_win_h() {
    let key = |vk: VIRTUAL_KEY, up: bool| INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT { wVk: vk, wScan: 0, dwFlags: if up { KEYEVENTF_KEYUP } else { KEYBD_EVENT_FLAGS(0) }, time: 0, dwExtraInfo: 0 },
        },
    };
    let inputs = [key(VK_LWIN, false), key(VK_H, false), key(VK_H, true), key(VK_LWIN, true)];
    unsafe {
        SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
    }
}
