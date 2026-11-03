// What the website does once it's loaded, for the English page and the Spanish one (es/). Each page
// sets window.LS first: its language, the path to the site's root, and its own words for what this
// script writes. Everything here only adds to a page that already reads in full without it.
(() => {
  const LS = window.LS || {};
  const W = LS.words || {};
  const root = LS.root || "";
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const still = matchMedia("(prefers-reduced-motion: reduce)");

  // The header stays on top of the page only while it covers less than a fifth of the screen: with
  // large text, or a phone on its side, it would hide what's being read, so it scrolls away instead.
  const top = document.querySelector("header.top");
  if (top) {
    const fit = () => top.classList.toggle("scrolls", top.offsetHeight > innerHeight / 5);
    new ResizeObserver(fit).observe(top);
    addEventListener("resize", fit);
    fit();
  }

  // Any input, any app: each input says what it does, and the signal runs along the line again.
  const any = document.getElementById("any");
  if (any) {
    const buttons = $$("button[data-any]", any);
    const out = document.getElementById("any-out");
    const line = any.querySelector(".flexline path");
    const show = (b) => {
      for (const x of buttons) x.setAttribute("aria-pressed", String(x === b));
      out.innerHTML = b.parentElement.querySelector(".any-says").innerHTML;
      any.dataset.input = b.dataset.any;
      if (line && !still.matches) {
        line.classList.remove("run");
        void line.getBoundingClientRect();   // start the drawing over
        line.classList.add("run");
      }
    };
    for (const b of buttons) b.addEventListener("click", () => show(b));
  }

  // The download for this computer goes first. A Mac's chip is guessed from its graphics, when the
  // browser says: Apple's own chips name themselves, Intel Macs name Intel. The choice stays the
  // reader's: every download is still there, with what it's for.
  const dl = document.querySelector("#download .btns");
  if (dl) {
    const pick = (() => {
      const ua = navigator.userAgent, platform = navigator.userAgentData?.platform || navigator.platform || "";
      if (/win/i.test(platform) || /Windows NT/.test(ua)) return "windows";
      if (!/mac/i.test(platform) || /iPhone|iPad/.test(ua)) return "";
      try {
        const gl = document.createElement("canvas").getContext("webgl");
        const info = gl && gl.getExtension("WEBGL_debug_renderer_info");
        const gpu = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "";
        if (/Intel|AMD|Radeon|NVIDIA/i.test(gpu) && !/Apple M\d/.test(gpu)) return "mac-intel";
      } catch { /* keep the usual first choice */ }
      return "mac-apple-silicon";
    })();
    const chosen = pick && dl.querySelector(`[data-os="${pick}"]`);
    if (chosen && chosen !== dl.firstElementChild) {
      for (const b of $$("[data-os]", dl)) b.classList.replace("btn-primary", "btn-ghost");
      chosen.classList.replace("btn-ghost", "btn-primary");
      dl.prepend(chosen);
    }
  }

  // Each Download link goes to that app's newest release, and the suite's version is its newest
  // release's. On Netlify the build writes them to releases.json; elsewhere they're asked of GitHub.
  // What's written in the page is kept when neither answers.
  (async () => {
    const links = $$("a[data-app]");
    const set = (suite, apps) => {
      if (suite) for (const s of $$("[data-suite]")) s.textContent = suite;
      for (const a of links) {
        const r = apps[a.dataset.app];
        if (!r) continue;
        a.href = r.url;
        const ver = a.querySelector(".ver");
        if (ver) ver.textContent = r.version;
      }
    };
    try {
      const res = await fetch(root + "releases.json", { cache: "no-cache" });
      if (res.ok) { const r = await res.json(); set(r.suite, r.apps || {}); return; }
    } catch { /* ask GitHub */ }
    try {
      const res = await fetch("https://api.github.com/repos/chittychitty38/limitless-sound/releases?per_page=100");
      if (!res.ok) return;
      const releases = (await res.json()).filter((r) => !r.draft && !r.prerelease);
      const suite = releases.find((x) => /^v\d/.test(x.tag_name));
      const apps = {};
      for (const a of links) {
        const r = releases.find((x) => x.tag_name.startsWith(a.dataset.app + "-v"));
        if (r) apps[a.dataset.app] = { version: r.tag_name.slice(a.dataset.app.length + 2), url: r.html_url };
      }
      set(suite && suite.tag_name.slice(1), apps);
    } catch { /* keep the written links */ }
  })();

  // The latest proof: a scoreboard, each app on each computer, the suite's own checks, and every
  // check in full. The results are data in English; the page's words are its own.
  const box = document.getElementById("proof-runs");
  if (!box) return;
  const shots = "https://raw.githubusercontent.com/chittychitty38/Limitless-sound/proof-results/";
  const name = (arch) => (W.computers || {})[arch] || arch;
  const short = (arch) => (W.short || {})[arch] || name(arch);
  const own = (t) => (LS.lang === "en" ? esc(t) : `<span lang="en">${esc(t)}</span>`);
  const checkName = (c) => ((W.checks || {})[c.id] ? esc(W.checks[c.id]) : own(c.check));
  const passed = (a) => !!a.level && (a.proof || []).every((x) => x.ok || x.warn);
  const why = (a) => {
    const bad = [...(a.checks || []), ...(a.proof || [])].find((x) => !x.ok && !x.warn && (x.level || "proof") !== "adaptive"
      && ["connected", "proof"].includes(x.level || "proof"));
    return bad ? `${checkName(bad)}: ${bad.detail ? own(bad.detail) : esc(W.failed)}` : esc(W.failed);
  };
  const mark = (ok) => `<span class="mark" aria-hidden="true">${ok ? "✓" : "✕"}</span><span class="vh">${esc(ok ? W.passed : W.failed)}: </span>`;
  const num = (n) => Number(n).toLocaleString(LS.lang, { maximumFractionDigits: 1 });

  const render = (data) => {
    const runs = data.runs || [];
    const done = runs.filter((r) => !r.error);
    const goodRun = (r) => !r.error && r.apps.every(passed) && (r.suite || []).every((s) => s.ok);
    // Every app and suite check, in the order the first finished run has them.
    const apps = [], checks = [];
    for (const r of done) {
      for (const a of r.apps) if (!apps.some((x) => x.tool === a.tool)) apps.push(a);
      for (const s of r.suite || []) if (!checks.some((x) => x.id === s.id)) checks.push(s);
    }
    const appOn = (r, tool) => (r.apps || []).find((a) => a.tool === tool);
    const checkOn = (r, id) => (r.suite || []).find((s) => s.id === id);
    const appsAll = apps.filter((a) => runs.every((r) => appOn(r, a.tool) && passed(appOn(r, a.tool)))).length;
    const checksAll = checks.filter((c) => runs.every((r) => checkOn(r, c.id)?.ok)).length;
    const slowest = Math.max(0, ...done.flatMap((r) => r.apps.map((a) => a.joinedSeconds || 0)));
    const first = done[0];
    const when = first ? new Date(first.when).toLocaleDateString(LS.lang, { day: "numeric", month: "long", year: "numeric" }) : "";

    const tile = (big, small, ok) => `<div${ok == null ? "" : ` class="${ok ? "ok" : "bad"}"`}><b>${big}</b><span>${small}</span></div>`;
    const sum = `<div class="proofsum">`
      + tile(W.of(runs.filter(goodRun).length, runs.length), esc(W.tiles.computers), runs.every(goodRun))
      + tile(W.of(appsAll, apps.length), esc(W.tiles.apps), appsAll === apps.length)
      + tile(W.of(checksAll, checks.length), esc(W.tiles.checks), checksAll === checks.length)
      + tile(`${num(slowest)}&nbsp;s`, esc(W.tiles.slowest), null)
      + `</div>`
      + (first ? `<p class="label proofwhen">Limitless Sound ${esc(first.suiteVersion)} · ${esc(when)}</p>` : "");

    const head = (first) => `<thead><tr><th scope="col">${esc(first)}</th>${runs.map((r) => `<th scope="col">${esc(short(r.arch))}</th>`).join("")}</tr></thead>`;
    const appRows = apps.map((a) => `<tr><th scope="row">${esc(a.name)}${a.version ? ` <span class="ver">${esc(a.version)}</span>` : ""}</th>`
      + runs.map((r) => {
        if (r.error) return `<td class="bad">${mark(false)}${esc(W.unfinished)}</td>`;
        const x = appOn(r, a.tool);
        if (!x) return `<td>—</td>`;
        if (!passed(x)) return `<td class="bad">${mark(false)}<small>${why(x)}</small></td>`;
        const idle = x.idle && x.idle.cpuPercent != null ? `<small>${esc(W.idle(num(x.idle.cpuPercent)))}</small>` : "";
        return `<td class="ok">${mark(true)}<span class="vh">${esc(W.readyIn)} </span>${num(x.joinedSeconds)}&nbsp;s${idle}</td>`;
      }).join("") + `</tr>`).join("");
    const checkRows = checks.map((c) => `<tr><th scope="row">${checkName(c)}</th>`
      + runs.map((r) => {
        const s = checkOn(r, c.id);
        return s ? `<td class="${s.ok ? "ok" : "bad"} tick">${mark(s.ok)}</td>` : `<td>—</td>`;
      }).join("") + `</tr>`).join("");
    const table = (caption, first, body) => `<div class="matrix" role="region" tabindex="0" aria-label="${esc(caption)}">`
      + `<table><caption>${esc(caption)}</caption>${head(first)}<tbody>${body}</tbody></table></div>`;

    // Each computer in full, as it was tested.
    const full = runs.map((run) => {
      if (run.error) return `<div class="proofrun"><h3>${esc(name(run.arch))}</h3><p>${esc(W.couldNot)} ${own(run.error)}</p></div>`;
      const ok = run.apps.filter(passed).length;
      const day = new Date(run.when).toLocaleDateString(LS.lang, { day: "numeric", month: "long", year: "numeric" });
      const hub = run.hubIdle && run.hubIdle.cpuPercent != null ? " " + esc(W.hub(run.hubVersion || "", num(run.hubIdle.cpuPercent))) : "";
      const list = run.apps.map((a) => {
        const good = passed(a);
        const how = good ? esc(W.how(num(a.joinedSeconds), a.actionsTried, a.idle && a.idle.cpuPercent != null ? num(a.idle.cpuPercent) : null)) : why(a);
        const shot = a.screenshot ? ` <a href="${shots}${esc(a.screenshot)}">${esc(W.screenshot)}</a>` : "";
        return `<li class="${good ? "ok" : "bad"}">${mark(good)}<span><b>${esc(a.name)}${a.version ? " " + esc(a.version) : ""}</b><span class="how">${how}${shot}</span></span></li>`;
      }).join("");
      const suite = (run.suite || []).map((s) => `<li class="${s.ok ? "ok" : "bad"}">${mark(s.ok)}<span><b>${checkName(s)}</b><span class="how">${own(s.detail)}</span></span></li>`).join("");
      return `<div class="proofrun"><h3>${esc(name(run.arch))}</h3>`
        + `<span class="label">${esc(run.computer.os)} · ${esc(day)} · Limitless Sound ${esc(run.suiteVersion)}</span>`
        + `<p class="fine">${esc(W.runLine(ok, run.apps.length, num(run.installSeconds)))}${hub}</p>`
        + `<ul class="prooflist">${list}</ul>`
        + (suite ? `<p class="fine">${esc(W.together)}</p><ul class="prooflist">${suite}</ul>` : "") + `</div>`;
    }).join("");

    box.innerHTML = sum
      + table(W.appsCaption, W.app, appRows)
      + `<p class="fine">${esc(W.appsNote)}</p>`
      + (checks.length ? table(W.checksCaption, W.check, checkRows) : "")
      + `<details class="proofall"><summary>${esc(W.inFull)}</summary><div class="proofruns">${full}</div></details>`;

    const chip = document.getElementById("proof-chip");
    if (chip && first) chip.textContent = W.chip(first.suiteVersion.replace(/^v/, ""), runs.filter(goodRun).length, runs.length);
  };

  fetch(root + "proof/latest.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((data) => {
      const link = document.getElementById("proof-run");
      if (data.run && link) link.href = data.run;
      render(data);
    })
    .catch(() => { box.innerHTML = `<p class="fine">${esc(W.none)}</p>`; });
})();
