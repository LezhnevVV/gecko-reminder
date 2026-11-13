// Lightweight card behavior checks without requiring a browser or HA.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function makeCard(entries = []) {
  const elements = new Map();
  const get = (selector) => {
    if (!elements.has(selector)) elements.set(selector, {
      textContent: '', innerHTML: '', disabled: false, closed: false,
      addEventListener() {}, close() { this.closed = true; },
    });
    return elements.get(selector);
  };
  let Card;
  const context = vm.createContext({
    HTMLElement: class {
      attachShadow() {
        this.shadowRoot = {innerHTML: '', addEventListener() {},
          querySelector: get, querySelectorAll: () => []};
      }
    },
    customElements: {get() {}, define(name, cls) { Card = cls; }},
    window: {}, Intl, Date, Map,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../custom_components/gecko_reminder/frontend/gecko-feeding-card.js'), 'utf8'), context);
  const card = new Card();
  card.setConfig({entity: 'sensor.gecko', title: '<img src=x onerror=alert(1)>'});
  card._today = () => '2024-02-29';
  card.hass = {config: {time_zone: 'UTC'}, states: {
    'sensor.gecko': {state: String(entries.length), attributes: {entries}},
  }};
  return {card, get};
}

test('Leap month displays all days, Monday offset, and today', () => {
  const {get} = makeCard();
  const html = get('#calendar').innerHTML;
  assert.equal((html.match(/data-date=/g) || []).length, 29);
  assert.equal((html.match(/class="day empty"/g) || []).length, 6);
  assert.match(html, /class="day today".*?data-date="2024-02-29"/);
});

test('Multiple feedings, month filtering, and HTML escaping', () => {
  const {card, get} = makeCard([
    {id: 'a', date: '2024-02-29', insect: 'cricket', count: 4, supplement: 'calcium', notes: '"><img src=x>'},
    {id: 'b', date: '2024-02-29', insect: 'dubia', count: 2, supplement: 'vitamins'},
    {id: 'c', date: '2024-03-01', insect: 'cricket', count: 7, supplement: 'none'},
  ]);
  assert.match(get('#summary').textContent, /2 кормлений · 6 насекомых/);
  assert.equal((get('#calendar').innerHTML.match(/class="feeding"/g) || []).length, 2);
  assert.ok(!get('#calendar').innerHTML.includes('<img'));
  assert.ok(!card.shadowRoot.innerHTML.includes('<img'));
});

test('Unavailable sensor disables adding entries', () => {
  const {card, get} = makeCard();
  card.hass = {states: {'sensor.gecko': {state: 'unavailable', attributes: {}}}};
  assert.equal(get('[data-action="add"]').disabled, true);
  assert.match(get('#status').textContent, /недоступен/);
});

test('State updates keep the form and its draft intact', () => {
  const {card} = makeCard();
  card._renderShell = () => { throw new Error('Form must not be rebuilt'); };
  card.hass = {states: {'sensor.gecko': {state: '0', attributes: {entries: []}}}};
});

test('Failed save keeps the dialog open and reports an error; retry can succeed', async () => {
  const {card, get} = makeCard();
  card._hass.callService = async () => { throw new Error('Storage failed'); };
  await card._save('save_feeding', {});
  assert.equal(get('dialog').closed, false);
  assert.equal(card._busy, false);
  assert.match(get('#form-error').textContent, /Storage failed/);
  card._hass.callService = async () => {};
  await card._save('save_feeding', {});
  assert.equal(get('dialog').closed, true);
});
