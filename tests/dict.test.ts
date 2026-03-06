import assert from "node:assert/strict";
import test from "node:test";

import { __resetDictionaryForTests, isPrefix, isWord, normalizeWord } from "../src/dict";

test("normalizeWord strips non a-z and lowercases", () => {
  assert.equal(normalizeWord("CAN'T"), "cant");
  assert.equal(normalizeWord("CO-OP"), "coop");
  assert.equal(normalizeWord("café"), "caf");
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

