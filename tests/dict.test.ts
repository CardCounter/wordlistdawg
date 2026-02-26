import assert from "node:assert/strict";
import test from "node:test";

import { __resetDictionaryForTests, isPrefix, isWord, normalizeWord } from "../src/dict";

test("normalizeWord strips non A-Z and uppercases", () => {
  assert.equal(normalizeWord("can't"), "CANT");
  assert.equal(normalizeWord("co-op"), "COOP");
  assert.equal(normalizeWord("café"), "CAF");
  assert.equal(normalizeWord("123"), "");
});

test("isWord throws before loadDictionary", () => {
  __resetDictionaryForTests();
  assert.throws(() => isWord("A"), /Dictionary not loaded/u);
});

test("isPrefix throws before loadDictionary", () => {
  __resetDictionaryForTests();
  assert.throws(() => isPrefix("QU"), /Dictionary not loaded/u);
});

