// Used by shared/hub/tests/test_clients.py: GazeStage-like app over the real hub.
const { Link } = require('./limitless-link');
const link = new Link({ tool: 'gaze', name: 'GazeStage', version: 'test',
  actions: [{ id: 'play', label: 'Play', intent: 'daw.play' }],
  onInvoke: async (action) => { link.did(action); return [true, 'js did ' + action]; }, retryMs: 100 });
link.on('connected', async (on) => {
  if (!on) return;
  const r = await link.invoke('daw.record');
  console.log('RESULT ' + JSON.stringify(r));
  link.state('tracking', true);
});
link.on('event', (name) => { if (name === 'control.ping') console.log('EVENT control.ping'); });
link.start();
setTimeout(() => process.exit(0), Number(process.argv[2] || 4000));
setInterval(() => {}, 1000);
