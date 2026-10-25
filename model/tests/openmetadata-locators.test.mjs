// C-22: model handle and catalog physical schema must resolve to the same manifest binding.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';

test('catalog locators match each connection schema binding in modeler.toml', () => {
  // Python 3.11+ tomllib parses the actual descriptors rather than a regex approximation.
  const data = JSON.parse(execFileSync('python3', ['-c', `
import json,tomllib
from pathlib import Path
root=Path.cwd()
connections=tomllib.loads((root/'model/connections.toml').read_text())['connection']
schemas=tomllib.loads((root/'modeler.toml').read_text())['schemas']
print(json.dumps([{'id':c['id'], 'locator':c['locators']['openmetadata'],
                  'physical':schemas[c['schema']]['db-schema']} for c in connections]))
`], { encoding: 'utf8' }));
  assert.equal(data.length, 2);
  for (const c of data) {
    assert.equal(c.locator.schema, c.physical, c.id);
    assert.equal(c.locator.service, 'hartland-pg', c.id);
  }
});
