//! macOS: runs the bundled `limitless-overlay` helper (Swift, ScreenCaptureKit +
//! Metal) and sends it the profile as a lookup table.

use std::path::PathBuf;

use color_core::lut::{Lut3D, DEFAULT_SIZE};
use color_core::Profile;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

pub struct Overlay {
    app: AppHandle,
    child: Option<CommandChild>,
    last_lut: Option<Vec<u8>>,
    shown: bool,
    flip: bool,
}

impl Overlay {
    pub fn new(app: AppHandle) -> Overlay {
        Overlay { app, child: None, last_lut: None, shown: false, flip: false }
    }

    fn ensure_running(&mut self) -> Result<(), String> {
        if self.child.is_some() {
            return Ok(());
        }
        let cmd = self.app.shell().sidecar("limitless-overlay").map_err(|e| format!("The screen filter helper is missing: {e}"))?;
        let (mut rx, child) = cmd.spawn().map_err(|e| format!("The screen filter helper didn't start: {e}"))?;
        let app = self.app.clone();
        tauri::async_runtime::spawn(async move {
            while let Some(ev) = rx.recv().await {
                match ev {
                    CommandEvent::Stdout(line) => {
                        let line = String::from_utf8_lossy(&line).trim().to_string();
                        if line == "error permission" {
                            let _ = app.emit(
                                "filter-error",
                                "Limitless Color needs Screen Recording permission to recolor the screen. Open System Settings › Privacy & Security › Screen & System Audio Recording, turn on Limitless Color, then switch the colors off and on again.",
                            );
                        } else if let Some(rest) = line.strip_prefix("error ") {
                            let _ = app.emit("filter-error", format!("The screen filter reported a problem: {rest}"));
                        }
                    }
                    CommandEvent::Terminated(_) => {
                        // Next time the colors are switched on, the helper is started again.
                        let _ = app.emit("filter-error", "The screen filter stopped. Switch the colors off and on to restart it.");
                    }
                    _ => {}
                }
            }
        });
        self.child = Some(child);
        self.last_lut = None;
        self.shown = false;
        Ok(())
    }

    fn send(&mut self, line: &str) -> Result<(), String> {
        let child = self.child.as_mut().ok_or("The screen filter helper isn't running.")?;
        if child.write(format!("{line}\n").as_bytes()).is_err() {
            self.child = None;
            return Err("The screen filter helper stopped responding.".into());
        }
        Ok(())
    }

    fn lut_path(&mut self) -> Result<PathBuf, String> {
        let dir = self.app.path().app_cache_dir().map_err(|e| e.to_string())?;
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        // Alternate between two files so the helper never reads one mid-write.
        self.flip = !self.flip;
        Ok(dir.join(if self.flip { "profile-a.lut" } else { "profile-b.lut" }))
    }
}

impl super::ScreenFilter for Overlay {
    fn kind(&self) -> &'static str {
        "overlay"
    }

    fn apply(&mut self, profile: &Profile, on: bool) -> Result<String, String> {
        if !on {
            if self.child.is_some() && self.shown {
                self.send("off")?;
            }
            self.shown = false;
            return Ok(String::new());
        }
        self.ensure_running()?;
        let bytes = Lut3D::from_profile(profile, DEFAULT_SIZE).to_rgba8();
        if self.last_lut.as_ref() != Some(&bytes) {
            let path = self.lut_path()?;
            std::fs::write(&path, &bytes).map_err(|e| e.to_string())?;
            self.send(&format!("lut {} {}", path.display(), DEFAULT_SIZE))?;
            self.last_lut = Some(bytes);
        }
        if !self.shown {
            self.send("on")?;
            self.shown = true;
        }
        Ok("Exact match to the tuner.".into())
    }
}

impl Drop for Overlay {
    fn drop(&mut self) {
        let _ = self.send("quit");
    }
}
