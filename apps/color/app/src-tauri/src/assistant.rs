//! Talks to Claude for the color assistant. Optional: without an API key the
//! built-in offline helper answers instead.

use std::time::Duration;

use serde_json::{json, Value};

use crate::words::{t, tf};

const MODEL: &str = "claude-opus-5-5";
const KEYRING_SERVICE: &str = "Limitless Color";
const KEYRING_USER: &str = "anthropic-api-key";

fn entry() -> Option<keyring::Entry> {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_USER).ok()
}

/// The person's Anthropic API key, kept in the Mac Keychain or Windows Credential Manager.
pub fn api_key() -> Option<String> {
    if let Ok(k) = std::env::var("ANTHROPIC_API_KEY") {
        if !k.is_empty() {
            return Some(k);
        }
    }
    entry()?.get_password().ok().filter(|k| !k.is_empty())
}

pub fn set_api_key(key: &str) -> Result<(), String> {
    let e = entry().ok_or_else(|| t("The system keychain isn't available."))?;
    if key.is_empty() {
        let _ = e.delete_credential();
        return Ok(());
    }
    e.set_password(key).map_err(|err| tf("Couldn't save the key: {error}", &[("error", &err.to_string())]))
}

/// Sends one assistant turn and returns Claude's text.
pub async fn ask_claude(key: &str, prompt: String) -> Result<String, String> {
    let body = json!({
        "model": MODEL,
        "max_tokens": 8000,
        "output_config": { "effort": "low" },
        "fallbacks": "default",
        "messages": [{ "role": "user", "content": prompt }],
    });
    let resp = reqwest::Client::new()
        .post("https://api.anthropic.com/v1/messages")
        .header("x-api-key", key)
        .header("anthropic-version", "2023-06-01")
        .header("anthropic-beta", "server-side-fallback-2026-07-01")
        .timeout(Duration::from_secs(90))
        .json(&body)
        .send()
        .await
        .map_err(|_| t("Couldn't reach Claude. Check the internet connection."))?;
    let code = resp.status();
    let v: Value = resp.json().await.map_err(|_| t("Claude sent an answer that couldn't be read."))?;
    if !code.is_success() {
        return Err(match code.as_u16() {
            401 | 403 => t("Claude didn't accept the API key."),
            429 => t("Claude is busy right now."),
            _ => tf("Claude returned an error ({code}).", &[("code", &code.to_string())]),
        });
    }
    if v["stop_reason"] == "refusal" {
        return Err(t("Claude declined to answer that."));
    }
    let text: String = v["content"]
        .as_array()
        .map(|blocks| blocks.iter().filter(|b| b["type"] == "text").filter_map(|b| b["text"].as_str()).collect())
        .unwrap_or_default();
    if text.is_empty() {
        return Err(t("Claude's answer was empty."));
    }
    Ok(text)
}
