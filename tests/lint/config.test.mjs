import assert from "node:assert/strict";
import test from "node:test";
import { checkConfig } from "../../.github/actions/lint/check-config.mjs";

const check = { name: "actionlint", script: "actionlint", tags: ["ci"] };
const config = (...jobs) => ({ "pre-commit": { jobs } });

test("a missing remote cannot silently remove a required check", () => {
  assert.throws(() => checkConfig(config(), ["actionlint"]), /missing/);
  assert.throws(() => checkConfig({}, ["actionlint"]), /pre-commit/);
});

test("empty or malformed expectations cannot produce a green no-op", () => {
  for (const expected of [[], null, {}, "actionlint", [""], [1]]) {
    assert.throws(() => checkConfig(config(check), expected), /nonempty/);
  }
});

test("checks must be runnable under the CI tag", () => {
  for (const job of [
    { ...check, tags: ["local"] },
    { ...check, skip: true },
    { name: "actionlint", tags: ["ci"] },
  ])
    assert.throws(() => checkConfig(config(job), ["actionlint"]), /missing/);
});

test("disabled groups and hooks cannot satisfy a required check", () => {
  const parent = { name: "validate", skip: true, group: { jobs: [check] } };
  assert.throws(() => checkConfig(config(parent), ["actionlint"]), /missing/);
  assert.throws(() => checkConfig({ "pre-commit": { skip: true, jobs: [check] } }, ["actionlint"]));
});

test("nested enabled checks are discovered without counting phase names", () => {
  const parent = { name: "validate", group: { jobs: [check] } };
  assert.deepEqual(checkConfig(config(parent), ["actionlint"]), ["actionlint"]);
  assert.throws(() => checkConfig(config(parent), ["validate"]), /missing/);
});

test("additional selected checks remain enabled; expectations are a minimum", () => {
  const shell = { name: "shellcheck", run: "shellcheck file.sh", tags: ["ci"] };
  assert.deepEqual(checkConfig(config(check, shell), ["actionlint"]), ["actionlint", "shellcheck"]);
});
