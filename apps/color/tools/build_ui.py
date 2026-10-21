"""Builds the desktop app's UI (app/ui/index.html) from the browser Color Tuner
page, adding the desktop controls: screen on/off, hold to compare, Talk,
the optional Claude key, and the bridge to the Rust side.

Usage: python3 tools/build_ui.py <color-tuner.html> app/ui/index.html
"""
import sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()


def rep(old, new, count=1):
    global s
    assert s.count(old) == count, f"expected {count}x: {old[:70]!r} (found {s.count(old)})"
    s = s.replace(old, new)


rep('<link rel="preconnect" href="https://fonts.googleapis.com">\n', "")
rep('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600;800&family=Atkinson+Hyperlegible+Mono:wght@400;600&display=swap">\n', "")
rep('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
rep("<style>\n", """<style>
@font-face{font-family:"Atkinson Hyperlegible Next";src:url(fonts/AtkinsonHyperlegibleNext.woff2) format("woff2");font-weight:200 800;font-display:swap}
@font-face{font-family:"Atkinson Hyperlegible Mono";src:url(fonts/AtkinsonHyperlegibleMono.woff2) format("woff2");font-weight:200 800;font-display:swap}
""")
rep("</style>\n", """input[type=password]{font:inherit;min-height:44px;padding:6px 10px;border-radius:8px;border:2px solid var(--line);background:var(--panel-2);color:var(--ink);flex:1;min-width:0}
details summary{cursor:pointer;min-height:44px;display:flex;align-items:center;font-weight:600}
#screenBtn[aria-pressed="true"]{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.note{margin:0;padding:10px 12px;border-radius:8px;background:var(--panel);border:1px solid var(--line)}
</style>
</head>
<body>
""")
s = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n' + s + "\n</body>\n</html>\n"

rep("""    <div class="row">
      <button id="undo" type="button">Undo</button>""", """    <div class="row">
      <button id="screenBtn" type="button" aria-pressed="false" hidden>Screen colors: Off</button>
      <button id="bypassBtn" type="button" hidden>Hold to compare</button>
      <button id="undo" type="button">Undo</button>""")
rep("  </header>\n", """  </header>
  <p class="note" id="screenNote" hidden aria-live="polite"></p>
""")
rep('<button id="stop" type="button" hidden>Stop</button>', '<button id="stop" type="button" hidden>Stop</button><button id="talkBtn" type="button" hidden>Talk</button>')
rep("""      </form>
    </section>""", """      </form>
      <details id="claudeBox" hidden>
        <summary>Smarter answers with Claude (optional)</summary>
        <p class="hint">Paste an Anthropic API key from console.anthropic.com. It's kept in your computer's keychain. Without a key, the built-in helper answers.</p>
        <div class="row"><input id="apiKey" type="password" autocomplete="off" placeholder="sk-ant-…" aria-label="Anthropic API key"><button id="saveKey" type="button">Save key</button></div>
        <p class="hint" id="keyMsg" aria-live="polite"></p>
      </details>
    </section>""")

# Bridge to the desktop app.
rep("""const clamp=(x,a,b)=>Math.min(b,Math.max(a,x));
""", """const clamp=(x,a,b)=>Math.min(b,Math.max(a,x));
const TAURI=window.__TAURI__;const desktop=!!(TAURI&&TAURI.core);
const invoke=desktop?TAURI.core.invoke:null;
let screenOn=false,bypass=false,platform="other";
""")

# While the screen filter is on, the screen does the recoloring, so the preview shows the source.
rep("""  T=makeTransform(S,anchors);
  const sim=$("#simOn").checked?simFn():null;
  if(srcData){
    const lutA=buildLut(sim?l=>sim(T(l)):T);""", """  T=makeTransform(S,anchors);
  const sim=$("#simOn").checked?simFn():null;
  const viaScreen=desktop&&screenOn;const showT=viaScreen?(l=>l):T;
  if(srcData){
    const lutA=buildLut(sim?l=>sim(showT(l)):showT);""")
rep("""    const sx=Math.round(view.width*$("#splitR").value/100);""", """    const sx=viaScreen?0:Math.round(view.width*$("#splitR").value/100);""")
rep("""    if(view.width-sx>90*u)tag("Yours",sx+10*u);""", """    if(view.width-sx>90*u&&!viaScreen)tag("Yours",sx+10*u);""")
rep("""    const outLin=T(hexToLin(it.from));const shown=sim?sim(outLin):outLin;""", """    const outLin=T(hexToLin(it.from));const disp=desktop&&screenOn?hexToLin(it.from):outLin;const shown=sim?sim(disp):disp;""")
rep("""  renderRoles(sim);renderFaders();persist();""", """  renderRoles(sim);renderFaders();persist();if(desktop)pushProfile();""")

# Assistant through the app (Claude with the person's key, or the offline helper in Rust).
rep("""async function ask(text){
  if(busy)return;busy=true;$("#send").disabled=true;""", """async function ask(text){
  if(desktop)return askDesktop(text);
  if(busy)return;busy=true;$("#send").disabled=true;""")
rep("""let sample=null,ctl=null,busy=false;
(async()=>{
  try{sample=window.claude?await window.claude.use("sample"):null}catch(e){sample=null}""", """let sample=null,ctl=null,busy=false;
(async()=>{
  if(desktop)return;
  try{sample=window.claude?await window.claude.use("sample"):null}catch(e){sample=null}""")

# Eye check runs with the screen filter off, so the test colors are shown as they are.
rep("""b.onclick=()=>{ck={i:0,score:{protan:0,deutan:0,tritan:0}};renderCheck()};body.appendChild(b);return;""",
    """b.onclick=async()=>{ck={i:0,score:{protan:0,deutan:0,tritan:0},resume:false};if(desktop&&screenOn){ck.resume=true;await setScreen(false)}renderCheck()};body.appendChild(b);return;""")
rep("""  if(ck.i>=CHECK.length){
""", """  if(ck.i>=CHECK.length){
    if(ck.resume){ck.resume=false;setScreen(true)}
""")

rep("""$("#dlCube").addEventListener("click",async()=>{
""", """$("#dlCube").addEventListener("click",async()=>{
  if(desktop){try{const p=await invoke("export_cube");$("#exportMsg").textContent="Saved to "+p}catch(e){$("#exportMsg").textContent=String(e)}return}
""")

rep("loadSample();\n})();", r"""loadSample();

/* ---------- desktop app ---------- */
function note(t){const n=$("#screenNote");n.textContent=t||"";n.hidden=!t}
function applyStatus(st){
  if(!bypass)screenOn=st.filterOn;platform=st.platform;
  const b=$("#screenBtn");b.setAttribute("aria-pressed",String(st.filterOn||bypass));b.textContent="Screen colors: "+(st.filterOn||bypass?"On":"Off");
  $("#bypassBtn").hidden=!(st.filterOn||bypass);
  $("#aiBadge").textContent=st.hasApiKey?"Claude":"Offline helper";
  $("#keyMsg").textContent=st.hasApiKey?"A key is saved. Save an empty box to remove it.":"";
  if(!bypass)note(st.filterOn?(st.filterNote||""):"");
  schedule();
}
let pushT=0;
function pushProfile(){clearTimeout(pushT);pushT=setTimeout(()=>invoke("set_profile",{profile:{S,anchors}}).catch(e=>note(String(e))),120)}
async function setScreen(on){try{applyStatus(await invoke("set_filter",{on}))}catch(e){note(String(e))}}
async function askDesktop(text){
  if(busy)return;busy=true;$("#send").disabled=true;
  addMsg("you",text);$("#ask").value="";
  const thinking=addMsg("bot","Thinking…");
  try{
    const r=await invoke("ask_assistant",{message:text});
    thinking.remove();snapshot();
    S={...DEFAULTS,...r.status.profile.S};anchors=r.status.profile.anchors||{};
    addMsg("bot",r.reply,{changes:r.changes.length?"Changed: "+r.changes.join(" · "):"",question:r.question});
    if(r.note)addMsg("bot",r.note);
    applyStatus(r.status);
  }catch(e){thinking.remove();addMsg("bot","Something went wrong: "+e)}
  busy=false;$("#send").disabled=false;
}
if(desktop){
  ["#screenBtn","#talkBtn","#claudeBox"].forEach(id=>$(id).hidden=false);
  document.querySelector('[aria-labelledby="p-h"]').innerHTML=`<h2 id="p-h">How it works</h2><div class="plan">
    <div><h3>Screen colors</h3><p>Switch them on and your profile is applied to the whole screen: Logic Pro, Pro Tools, plugins and everything else. Closing this window keeps them on. Use the menu bar or tray icon to switch them off or quit.</p></div>
    <div><h3>Quick switch</h3><p id="shortcutHelp"></p></div>
    <div><h3>Talk instead of typing</h3><p>Press Talk, then speak. It uses your computer's own dictation, so any microphone that works with your computer works here.</p></div></div>`;
  $(".split").hidden=true;
  $("#screenBtn").addEventListener("click",()=>setScreen(!($("#screenBtn").getAttribute("aria-pressed")==="true")));
  const holdOn=async()=>{if(bypass||!screenOn)return;bypass=true;note("Showing the original colors. Let go to see yours.");try{await invoke("set_filter",{on:false})}catch(e){}};
  const holdOff=async()=>{if(!bypass)return;bypass=false;await setScreen(true)};
  const bp=$("#bypassBtn");bp.addEventListener("pointerdown",holdOn);["pointerup","pointerleave","pointercancel"].forEach(ev=>bp.addEventListener(ev,holdOff));
  bp.addEventListener("keydown",e=>{if((e.key===" "||e.key==="Enter")&&!e.repeat){e.preventDefault();holdOn()}});
  bp.addEventListener("keyup",e=>{if(e.key===" "||e.key==="Enter")holdOff()});
  $("#talkBtn").addEventListener("click",async()=>{$("#ask").focus();try{await invoke("start_dictation")}catch(e){}
    note(platform==="mac"?"Speak now. If nothing happens, press the Fn key twice, or turn on Dictation in System Settings › Keyboard.":"Speak now. If nothing happens, press Windows key + H.")});
  $("#saveKey").addEventListener("click",async()=>{try{await invoke("set_api_key",{key:$("#apiKey").value});$("#apiKey").value="";applyStatus(await invoke("get_status"))}catch(e){$("#keyMsg").textContent=String(e)}});
  document.querySelector('#e-h').closest(".card").querySelector(".hint").textContent="Your settings are saved automatically. You can also save them as a .cube color profile in Documents › Limitless Color, to share or back up.";
  $("#dlCube").textContent="Save .cube profile";
  TAURI.event.listen("status",e=>applyStatus(e.payload));
  TAURI.event.listen("filter-error",e=>note(e.payload));
  invoke("get_status").then(st=>{
    S={...DEFAULTS,...st.profile.S};anchors=st.profile.anchors||{};
    const k=st.shortcut.replace("CommandOrControl",st.platform==="mac"?"Command":"Ctrl").replace("Alt",st.platform==="mac"?"Option":"Alt").split("+").join(" + ");
    $("#shortcutHelp").textContent="Press "+k+" from any app to switch the screen colors on or off.";
    applyStatus(st);
  });
}
})();""")

open(dst, "w", encoding="utf-8").write(s)
print("wrote", dst, len(s), "bytes")
