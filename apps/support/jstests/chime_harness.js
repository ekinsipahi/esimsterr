// Does the chat widget make a sound at the right moments?
//
// Run by apps/support/tests_widget_chime.py, which renders the real widget,
// pulls its script out of the page and hands the path in as argv[2]. Nothing
// here is a copy of the widget: if the widget changes, this runs against the
// change.
//
// A chime is counted by the oscillators it builds -- three per ring -- because
// what a listener would hear is the only thing worth asserting, and stubbing
// the function itself would test the stub.
const fs = require('fs');

let rings = 0, timers = [], fetches = [], reply = null, seenFlags = [];

function el(id) {
  return {
    id, textContent: '', innerHTML: '', value: '', hidden: false,
    style: {}, dataset: {},
    setAttribute() {}, addEventListener(ev, fn) { this['on_' + ev] = fn; },
    appendChild() {}, insertAdjacentHTML() {}, focus() {},
    scrollTop: 0, scrollHeight: 0, clientHeight: 0, disabled: false,
  };
}
const nodes = {};
for (const id of ['asst-launcher', 'asst-panel', 'asst-body', 'asst-input', 'asst-send',
                  'asst-badge', 'asst-status', 'asst-greeting', 'asst-mute', 'asst-close']) {
  nodes[id] = el(id);
}

global.document = {
  cookie: 'csrftoken=abc',
  visibilityState: 'visible',
  getElementById: (id) => nodes[id] || null,
  addEventListener() {},
};
global.requestAnimationFrame = (fn) => fn();
global.localStorage = { store: {}, getItem(k) { return this.store[k] ?? null; },
                        setItem(k, v) { this.store[k] = v; } };

// Counting oscillators is how we hear it: one chime builds three.
let oscillators = 0;
function FakeCtx() {
  this.state = 'running';
  this.currentTime = 0;
  this.destination = {};
  this.createGain = () => ({ gain: { value: 0, setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} });
  this.createBiquadFilter = () => ({ type: '', frequency: { value: 0 }, connect() {} });
  this.createOscillator = () => { oscillators++; return { type: '', frequency: { setValueAtTime() {} }, connect() {}, start() {}, stop() {} }; };
  this.resume = () => {};
}
global.AudioContext = FakeCtx;
global.window = { addEventListener() {}, AudioContext: FakeCtx };

global.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
global.clearTimeout = () => {};

global.fetch = (url) => {
  fetches.push(url);
  seenFlags.push(url.includes('seen=1'));
  return Promise.resolve({ ok: true, json: () => Promise.resolve(reply) });
};

function conv(messages, extra = {}) {
  return { id: 'c1', status: 'open', owner_joined: false, unread: 0, messages, ...extra };
}
const USER = (t) => ({ role: 'user', content: t, created_at: '2026-09-17T10:00:00Z' });
const AI = (t) => ({ role: 'assistant', content: t, created_at: '2026-09-17T10:00:01Z' });
const OP = (t) => ({ role: 'owner', content: t, created_at: '2026-09-17T10:00:02Z' });

function ringsDuring(fn) {
  const before = oscillators;
  fn();
  return (oscillators - before) / 3;
}
const flush = () => new Promise((r) => setImmediate(r));

// Pick the polling timer specifically. openPanel also schedules a 60 ms
// focus(), so popping the last one scheduled fires the wrong thing.
function takePoll() {
  for (let i = timers.length - 1; i >= 0; i--) {
    if (timers[i].ms === 6000 || timers[i].ms === 20000 || timers[i].ms > 50000) {
      return timers.splice(i, 1)[0];
    }
  }
  throw new Error('no polling timer scheduled');
}

// Load the widget, with its own first GET already primed.
reply = conv([USER('hello'), AI('hi there')]);
eval(fs.readFileSync(process.argv[2], 'utf8'));

(async () => {
  const checks = [];
  const check = (name, got, want) => {
    checks.push({ name, got, want, ok: got === want });
  };

  await flush();
  check('page load with existing messages is silent', oscillators / 3, 0);

  // Opening the panel: everything in there is history.
  let n = oscillators;
  nodes['asst-launcher'].on_click();
  await flush();
  check('opening the panel is silent', (oscillators - n) / 3, 0);

  // A poll that brings an operator reply: this is the one that must ring.
  n = oscillators;
  reply = conv([USER('hello'), AI('hi there'), OP('This is Ekin from support.')]);
  const poll = takePoll();
  poll.fn();
  await flush();
  check('an operator reply arriving rings', (oscillators - n) / 3, 1);

  // A poll that brings nothing new.
  n = oscillators;
  takePoll().fn();
  await flush();
  check('a poll with no new message is silent', (oscillators - n) / 3, 0);

  // The visitor sends something and the AI answers in the same response.
  n = oscillators;
  nodes['asst-input'].value = 'my esim will not connect';
  nodes['asst-send'].on_click();
  reply = conv([USER('hello'), AI('hi there'), OP('This is Ekin from support.'),
                USER('my esim will not connect'), AI('Turn data roaming on.')]);
  await flush(); await flush();
  check('the answer to your own message is silent', (oscillators - n) / 3, 0);

  // Hidden tab: still polls, still rings, and must NOT mark anything seen.
  n = oscillators;
  seenFlags = [];
  document.visibilityState = 'hidden';
  reply = conv([USER('hello'), AI('hi there'), OP('This is Ekin from support.'),
                USER('my esim will not connect'), AI('Turn data roaming on.'),
                OP('Still there?')], { unread: 1 });
  takePoll().fn();
  await flush();
  check('a hidden tab keeps polling, slower', takePoll().ms, 20000);
  check('a reply to a hidden tab rings', (oscillators - n) / 3, 1);
  check('a hidden tab never marks a reply as seen', seenFlags.some(Boolean), false);
  check('the badge survives for when they come back', nodes['asst-badge'].textContent, '1');

  // Muted.
  document.visibilityState = 'visible';
  nodes['asst-mute'].on_click();          // mute (this click itself is silent)
  n = oscillators;
  reply = conv([USER('a'), OP('b'), OP('c')]);
  takePoll().fn();
  await flush();
  check('muted means silent', (oscillators - n) / 3, 0);

  let bad = 0;
  for (const c of checks) {
    if (!c.ok) bad++;
    console.log(`  ${c.ok ? 'PASS' : 'FAIL'}  ${c.name}` + (c.ok ? '' : `  (got ${c.got}, wanted ${c.want})`));
  }
  console.log(bad ? `\n${bad} FAILED` : `\nall ${checks.length} passed`);
  process.exit(bad ? 1 : 0);
})();
