//! macOS: runs the bundled `limitless-overlay` helper (Swift, ScreenCaptureKit +
//! Metal) and sends it the profile as a lookup table.

use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

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
    /// Counts helper starts, so a helper we stopped on purpose isn't reported as a crash.
    generation: Arc<AtomicU64>,
}

impl Overlay {
    pub fn new(app: AppHandle) -> Overlay {
        Overlay { app, child: None, last_lut: None, shown: false, flip: false, generation: Arc::default() }
    }

    fn ensure_running(&mut self) -> Result<(), String> {
        if self.child.is_some() {
            return Ok(());
        }
        let cmd = self.app.shell().sidecar("limitless-overlay").map_err(|e| format!("The screen filter helper is missing: {e}"))?;
        let (mut rx, child) = cmd.spawn().map_err(|e| format!("The screen filter helper didn't start: {e}"))?;
        let app = self.app.clone();
        let generation = self.generation.clone();
        let mine = generation.fetch_add(1, Ordering::SeqCst) + 1;
        tauri::async_runtime::spawn(async move {
            while let Some(ev) = rx.recv().await {
                match ev {
                    CommandEvent::Stdout(line) => {
                        let line = String::from_utf8_lossy(&line).trim().to_string();
                        if line == "error permission" {
                            // The window walks the person through allowing it.
                            let _ = app.emit("permission-needed", ());
                        } else if let Some(rest) = line.strip_prefix("error ") {
                            let _ = app.emit("filter-error", format!("The screen filter reported a problem: {rest}"));
                        }
                    }
                    CommandEvent::Terminated(_) if generation.load(Ordering::SeqCst) == mine => {
                        // Next time the colors are switched on, the helper is started again.
                        let _ = app.emit("filter-stopped", ());
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

    /// Stops the helper. The next `apply` starts a fresh one, which picks up a
    /// Screen Recording permission granted since the last start.
    fn restart(&mut self) {
        self.generation.fetch_add(1, Ordering::SeqCst);
        let _ = self.send("quit");
        self.child = None;
        self.shown = false;
        self.last_lut = None;
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

/// Asks a one-shot copy of the helper whether Screen Recording is allowed.
/// With `request`, macOS also shows its prompt (first time only) and lists the app in System Settings.
pub async fn screen_permission(app: &AppHandle, request: bool) -> Result<bool, String> {
    let flag = if request { "--request-permission" } else { "--check-permission" };
    let out = app
        .shell()
        .sidecar("limitless-overlay")
        .map_err(|e| format!("The screen filter helper is missing: {e}"))?
        .args([flag])
        .output()
        .await
        .map_err(|e| format!("Couldn't check Screen Recording permission: {e}"))?;
    Ok(String::from_utf8_lossy(&out.stdout).trim() == "granted")
}

impl Drop for Overlay {
    fn drop(&mut self) {
        let _ = self.send("quit");
    }
}
