// The window's side of the built-in instrument, which plays in a hidden page of its own
// (synth-page.js; main.js says why). The same calls as Synth, passed on there: nothing here
// waits for the computer's audio.
export class SynthLink {
  constructor(bridge) {
    this.port = null; this.waiting = []; this.preset = 'keys'; this.volume = 0.9;
    addEventListener('message', (e) => {
      if (e.source !== window || e.data !== 'gazestage:synth-port') return;
      this.port?.close(); this.port = e.ports[0];
      // The instrument's page (a new one too, if it had to be replaced) starts with the sound chosen here.
      this.port.postMessage({ op: 'preset', name: this.preset });
      this.port.postMessage({ op: 'volume', value: this.volume });
      // Pressed while GazeStage was starting: they count from now, so they still sound.
      for (const m of this.waiting.splice(0)) this.port.postMessage({ ...m, at: Date.now() });
    });
    bridge.connect();
  }

  send(m) {
    m.at = Date.now();
    if (this.port) this.port.postMessage(m);
    else if (this.waiting.length < 64) this.waiting.push(m);   // until the channel is there, at start
  }

  noteOn(note, velocity = 100) { this.send({ op: 'noteOn', note, velocity }); }
  noteOff(note) { this.send({ op: 'noteOff', note }); }
  allOff() { this.send({ op: 'allOff' }); }
  tick() { this.send({ op: 'tick' }); }
  warm() { this.send({ op: 'warm' }); }
  setPreset(name) { this.preset = name; if (this.port) this.send({ op: 'preset', name }); }
  setVolume(value) { this.volume = value; if (this.port) this.send({ op: 'volume', value }); }
}
