#!/usr/bin/env node
// node scripts/observe.mjs runs/.../answers.jsonl -> observation-only JSONL.
import fs from 'node:fs';
import { QualityObserver } from '../runtime/quality.mjs';

if (!process.argv[2]) {
  console.error('Usage: node scripts/observe.mjs path/to/answers.jsonl');
  process.exit(1);
}
const observer = new QualityObserver();
for (const line of fs.readFileSync(process.argv[2], 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/).filter(Boolean)) {
  const row = JSON.parse(line);
  if (row.status !== 'ok') continue;
  const sessionKey = row.session || row.id;
  const result = observer.inspect(row.action === 'no_reply' ? [] : [row.answer], { sessionKey });
  console.log(JSON.stringify({ id: row.id, action: result.action, flags: result.flags, human_review: 'pending' }));
  // Offline turn completion, not a production delivery receipt. No host sender is called.
  if (row.action === 'reply') observer.confirmDelivered(sessionKey, [row.answer]);
}
