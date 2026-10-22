// MIDI routing. In the desktop app on macOS/Linux, GazeStage owns virtual ports
// ("GazeStage Notes", "GazeStage HUI") so nothing needs setting up. Otherwise (Windows, or a
// browser) it uses Web MIDI with loopback ports the player picks, auto-picking likely names.
import { HUI, HuiParser, huiSwitch } from './lib.js';

// Line 6 hardware that takes MIDI over USB: Helix, HX Stomp, HX Effects, POD Go.
const LINE6 = /helix|hx stomp|hx effects|pod go|line ?6/i;

const GUESS = {
  notes: /gazestage notes|notes/i,
  huiOut: /to pro tools|gazestage hui|hui/i,
  huiIn: /from pro tools|gazestage hui|hui/i,
};

export class MidiRouter extends EventTarget {
  constructor(store) {
    super();
    this.store = store;
    this.mode = 'none';            // 'native' | 'web' | 'none'
    this.access = null;
    this.parser = new HuiParser();
    this.lastPing = -Infinity;
    this.leds = new Map();         // `${zone}:${port}` -> on
    this.sel = { notes: store.get('midi.notes', ''), huiOut: store.get('midi.huiOut', ''), huiIn: store.get('midi.huiIn', '') };
    this.useBuiltIn = store.get('midi.useBuiltIn', true);
    this.nativePorts = null;
  }

  async init() {
    const bridge = window.gazestage?.midi;
    if (bridge) {
      const st = await bridge.status();
      this.nativeError = st.error;
      if (st.native) {
        this.mode = 'native'; this.nativePorts = st.ports;
        bridge.onHuiIn((bytes) => this.onHuiBytes(bytes, (b) => bridge.send('hui', b)));
        this.emit(); return;
      }
    }
    if (!navigator.requestMIDIAccess) { this.mode = 'none'; this.error = 'This browser has no MIDI'; this.emit(); return; }
    try {
      this.access = await navigator.requestMIDIAccess({ sysex: false });
      this.mode = 'web';
      this.access.onstatechange = () => { this.autoPick(); this.hookInput(); this.emit(); };
      this.autoPick(); this.hookInput();
    } catch (e) {
      this.mode = 'none';
      this.error = e.name === 'NotAllowedError' ? 'MIDI permission denied' : 'No MIDI system found';
    }
    this.emit();
  }

  emit() { this.dispatchEvent(new Event('change')); }

  ports(kind) {
    if (!this.access) return [];
    return [...(kind === 'huiIn' ? this.access.inputs : this.access.outputs).values()].map(p => ({ id: p.id, name: p.name }));
  }
  choose(kind, id) { this.sel[kind] = id; this.store.set('midi.' + kind, id); if (kind === 'huiIn') this.hookInput(); this.emit(); }
  autoPick() {
    for (const kind of Object.keys(this.sel)) {
      const list = this.ports(kind);
      if (this.sel[kind] && list.some(p => p.id === this.sel[kind])) continue;
      const hit = list.find(p => GUESS[kind].test(p.name));
      if (hit) this.sel[kind] = hit.id;
    }
  }
  hookInput() {
    if (!this.access) return;
    for (const p of this.access.inputs.values()) p.onmidimessage = null;
    const inp = this.sel.huiIn && this.access.inputs.get(this.sel.huiIn);
    if (inp) inp.onmidimessage = (e) => this.onHuiBytes(e.data, (b) => this.webOut('huiOut')?.send(b));
  }
  webOut(kind) { return this.access && this.sel[kind] ? this.access.outputs.get(this.sel[kind]) : null; }

  onHuiBytes(bytes, reply) {
    for (const ev of this.parser.feed(bytes)) {
      if (ev.type === 'ping') { reply(HUI.PING_REPLY); this.lastPing = performance.now(); }
      else if (ev.type === 'led') {
        this.leds.set(`${ev.zone}:${ev.port}`, ev.on);
        this.dispatchEvent(new CustomEvent('led', { detail: ev }));
      }
    }
  }

  get proToolsConnected() { return performance.now() - this.lastPing < 2500; }
  get canSendHui() { return this.mode === 'native' || !!this.webOut('huiOut'); }
  get notesTarget() { return this.mode === 'native' ? this.nativePorts.notes : this.webOut('notes')?.name || null; }

  sendHui(bytes) {
    if (this.mode === 'native') { window.gazestage.midi.send('hui', bytes); return true; }
    const o = this.webOut('huiOut'); if (!o) return false; o.send(bytes); return true;
  }
  transport(port, down) { return this.sendHui(huiSwitch(HUI.TRANSPORT_ZONE, port, down)); }

  // ---------- tone pad output ----------
  // choice: 'auto' (a connected Line 6 device, otherwise the notes port), 'notes', or the name
  // of a hardware output. Resolved again whenever ports come and go.
  async toneOutputs() {
    if (this.mode === 'native') return (await window.gazestage.midi.outputs()).map(name => ({ id: name, name }));
    return this.access ? [...this.access.outputs.values()].map(p => ({ id: p.id, name: p.name })) : [];
  }
  async resolveTone(choice) {
    const list = await this.toneOutputs();
    let pick = null;
    if (choice === 'auto') pick = list.find(p => LINE6.test(p.name)) || null;
    else if (choice !== 'notes') pick = list.find(p => p.id === choice || p.name === choice) || null;
    this.toneMissing = choice !== 'auto' && choice !== 'notes' && !pick ? choice : null;
    if (this.mode === 'native') {
      const want = pick?.name || '';
      if (want !== (this.toneOpen || '')) {
        const r = await window.gazestage.midi.openTone(want);
        this.toneOpen = r.ok ? want : '';
      }
      this.toneName = this.toneOpen || this.nativePorts?.notes || null;
    } else {
      this.toneId = pick?.id || null;
      this.toneName = pick?.name || this.webOut('notes')?.name || null;
    }
    return this.toneName;
  }
  sendTone(bytes) {
    if (!bytes.length) return true;
    if (this.mode === 'native') { window.gazestage.midi.send(this.toneOpen ? 'tone' : 'notes', bytes); return true; }
    const o = (this.toneId && this.access?.outputs.get(this.toneId)) || this.webOut('notes');
    if (!o) return false; o.send(bytes); return true;
  }

  sendNotes(bytes) {
    if (this.mode === 'native') { window.gazestage.midi.send('notes', bytes); return true; }
    const o = this.webOut('notes'); if (!o) return false; o.send(bytes); return true;
  }
}
