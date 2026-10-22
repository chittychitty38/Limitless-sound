// The built-in instrument's own page: hidden, in a process of its own (main.js). Making an audio
// context holds up the page that makes it until the computer's audio device answers, up to 20 s
// on a Mac with no working sound output. Here that only holds up the sound, never the window
// that follows the pointer and answers other apps. Its messages come from synth-link.js.
import { Synth } from './synth.js';

const synth = new Synth();
// Notes and clicks are never played late: one that waited over a quarter second to reach this
// page (say, while the audio started for an earlier one) is dropped, and so is one whose own
// start of the audio took over a second (a device that doesn't answer). Note-offs and settings
// always apply.
const late = (m, ms) => Date.now() - m.at > ms;
let port = null;

addEventListener('message', (e) => {
  if (e.source !== window || e.data !== 'gazestage:synth-port') return;
  port?.close(); port = e.ports[0];
  synth.allOff();   // the window started again (say, after a reset): nothing it held keeps sounding
  port.onmessage = ({ data: m }) => {
    switch (m.op) {
      case 'noteOn': if (!late(m, 250)) { synth.ensure(); if (!late(m, 1000)) synth.noteOn(m.note, m.velocity); } break;
      case 'tick': if (!late(m, 250)) { synth.ensure(); if (!late(m, 1000)) synth.tick(); } break;
      case 'warm': synth.warm(); break;
      case 'noteOff': synth.noteOff(m.note); break;
      case 'allOff': synth.allOff(); break;
      case 'preset': synth.setPreset(m.name); break;
      case 'shape': synth.shape(m.x, m.y); break;
      case 'volume': synth.setVolume(m.value); break;
    }
  };
});
window.__synth = synth;   // for the smoke test
