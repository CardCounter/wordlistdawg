import assert from "node:assert/strict";
import test from "node:test";

import { assertSortedUnique, parseWordsFile } from "../scripts/build_dawg.mjs";

test("parseWordsFile trims and skips empty lines", () => {
  const words = parseWordsFile("A\n\nB \r\n C\n");
  assert.deepEqual(words, ["A", "B", "C"]);
});

test("assertSortedUnique accepts sorted unique lists", () => {
  assert.doesNotThrow(() => assertSortedUnique(["A", "I", "QI"]));
});

test("assertSortedUnique rejects duplicates", () => {
  assert.throws(() => assertSortedUnique(["A", "A", "B"]), /sorted and unique/u);
});

test("assertSortedUnique rejects unsorted lists", () => {
  assert.throws(() => assertSortedUnique(["A", "CAT", "CAR"]), /sorted and unique/u);
});

