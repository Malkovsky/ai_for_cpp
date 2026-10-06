// Offline interaction checks. Usage: node test_viewer.js <report directory>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const report = process.argv[2];
const model = JSON.parse(fs.readFileSync(path.join(report, 'model.json'), 'utf8'));
const html = fs.readFileSync(path.join(report, 'index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, {
      value: id === 'sort' ? 'self_weight' : '', innerHTML: '', textContent: '', disabled: false,
    });
    return elements.get(id);
  },
};
vm.runInNewContext(script, { document });
const get = id => elements.get(id);
const event = dataset => ({ target: { closest: () => ({ dataset }) } });
const percent = weight => (100 * weight / model.root.weight).toFixed(2) + '%';
assert.ok(get('view').innerHTML.includes('<svg'));
const rootDetails = get('details').innerHTML;
const selected = model.root.children[0];
get('view').onclick(event({ id: selected.id }));
assert.equal(get('back').disabled, false);
get('back').onclick();
assert.equal(get('details').innerHTML, rootDetails);
get('search').oninput({ target: { value: '.' } });
assert.ok(get('view').innerHTML.includes('search-hit'));
assert.ok(get('match').textContent.includes('100.00%'));
get('search').oninput({ target: { value: '[' } });
assert.equal(get('error').textContent, 'Invalid regular expression');
get('clear').onclick();
assert.equal(get('error').textContent, '');
assert.equal(get('match').textContent, '');
get('layout').onchange({ target: { value: 'icicle' } });
assert.ok(get('view').innerHTML.includes('y="7"'));
get('direction').onchange({ target: { value: 'reverse' } });
assert.ok(get('frame-name').textContent.includes('bottom-up'));
get('direction').onchange({ target: { value: 'root' } });
get('sort').value = 'weight';
get('sort').onchange();
assert.ok(get('hotspots').innerHTML.includes('data-name='));

const functions = Object.values(model.functions).filter(fn => fn.definition);
assert.ok(functions.length, 'Use a report with resolved definitions for source tests');
const fn = functions.find(fn => fn.calls.some(c => c.line)) || functions[0];
get('hotspots').onclick(event({ name: fn.name }));
assert.ok(get('details').innerHTML.includes(percent(fn.total_weight)));
assert.ok(get('details').innerHTML.includes(percent(fn.self_weight)));
assert.ok(get('source').innerHTML.includes('Full function'));
assert.ok(!get('source').innerHTML.includes('code-gap'));
const lines = [...get('source').innerHTML.matchAll(/class="line-number">(\d+) :/g)].map(m => +m[1]);
assert.equal(lines[0], fn.definition.start);
assert.equal(lines.at(-1), fn.definition.end);
assert.ok(lines.every((line, i) => !i || line === lines[i - 1] + 1));
const call = fn.calls.find(c => c.line);
if (call) {
  assert.ok(get('source').innerHTML.includes(`data-call-line="${call.line}"`));
  get('source').onclick(event({ callLine: call.line, callPath: call.path, function: fn.name }));
  const largest = fn.calls.filter(c => c.line === call.line && c.path === call.path)
    .reduce((a, b) => a.weight > b.weight ? a : b);
  assert.equal(get('frame-name').textContent, largest.callee);
}
get('reset').onclick();
assert.equal(get('details').innerHTML, rootDetails);
console.log('Viewer navigation, percentages and contiguous function bodies passed.');
