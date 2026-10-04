// Validates schemas/examples against the spec schema: valid/ must pass, invalid/ must fail.
// Python runs the same examples (D31), so both sides agree on what a spec is.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Ajv2020 } from 'ajv/dist/2020.js';

const root = join(import.meta.dirname, '..', '..', 'schemas');
const schema = JSON.parse(readFileSync(join(root, 'test-spec.schema.json'), 'utf8'));
const validate = new Ajv2020({ strict: false }).compile(schema);

let failures = 0;
for (const kind of ['valid', 'invalid'] as const) {
  const dir = join(root, 'examples', kind);
  for (const file of readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    const ok = validate(JSON.parse(readFileSync(join(dir, file), 'utf8')));
    if (ok !== (kind === 'valid')) {
      failures++;
      console.error(`FAIL ${kind}/${file}`, validate.errors ?? '');
    } else {
      console.log(`ok   ${kind}/${file}`);
    }
  }
}
process.exit(failures ? 1 : 0);
