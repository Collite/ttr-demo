// BI-4 (⚑BI-4-A) — the returns dataset's entity in the COMMITTED ARCHIVE: its labels only, no phrase.
//
// `er.entity.category_return_month` (stacked on `er.query.returns_monthly_by_category`, model/er/returns-by-category.ttrm) is
// the dataset of Superset's "Returns by category" dashboard. The Golem already answers returns questions over the return
// family itself (`return_request` is «reklamace»), so nothing declares a phrase for it: a returns phrase on it would be
// the longer span and take those questions from the entities they bind today.
//
// Run: node --test lexicon/tests/bi-returns.test.mjs   (or `just verify-model`)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isCs, lexicon } from './archive.mjs';

const ENTITY = 'er.entity.category_return_month';

test('BI-4 — the returns dataset is reached by its two labels and by nothing declared', () => {
  const rows = lexicon.entries.filter((e) => e.targetRef === ENTITY || e.targetRef.startsWith(`${ENTITY}.`));
  assert.deepEqual(rows.filter((e) => e.sourceTag !== 'METADATA').map((e) => `«${e.termNormalized}» ${e.sourceTag}`), []);
  assert.ok(rows.length >= 2, `the entity's labels did not reach the archive: ${rows.map((e) => e.termNormalized).join(', ')}`);
});

test('control — «reklamace» is still the return request, and only it', () => {
  const refs = lexicon.entries.filter((e) => e.termNormalized === 'reklamace' && isCs(e)).map((e) => e.targetRef);
  assert.deepEqual([...new Set(refs)], ['er.entity.return_request']);
});
