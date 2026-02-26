import crypto from "node:crypto";
import fs from "node:fs/promises";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..");
const WORDS_PATH = path.join(ROOT, "words.txt");
const OUT_PATH = path.join(ROOT, "dict.dawg");
const META_PATH = path.join(ROOT, "dict.meta.json");
const DAWG_FILE_NAME = "dict.dawg";
const LICENSES_DIR = path.join(ROOT, "licenses");
const DAWG_LICENSE_DEST = path.join(LICENSES_DIR, "DAWG-LOOKUP-LICENSE.txt");

class ProgressTracker {
  constructor(totalSteps) {
    this.totalSteps = totalSteps;
    this.currentStep = 0;
    this.startedAt = performance.now();
  }

  start(title, detail) {
    this.currentStep += 1;
    console.log(`[${this.currentStep}/${this.totalSteps}] ${title}`);
    if (detail) {
      console.log(`    ${detail}`);
    }
    return performance.now();
  }

  done(startedAt, detail) {
    const elapsedSec = (performance.now() - startedAt) / 1000;
    if (detail) {
      console.log(`    done in ${elapsedSec.toFixed(1)}s (${detail})`);
    } else {
      console.log(`    done in ${elapsedSec.toFixed(1)}s`);
    }
  }

  summary() {
    const elapsedSec = (performance.now() - this.startedAt) / 1000;
    console.log(`[complete] DAWG build finished in ${elapsedSec.toFixed(1)}s`);
  }
}

function sha256Hex(input) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

export function parseWordsFile(contents) {
  return contents
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function assertSortedUnique(words) {
  for (let i = 1; i < words.length; i += 1) {
    if (words[i - 1] >= words[i]) {
      throw new Error(
        `words.txt must be strictly sorted and unique. Index ${i - 1}='${words[i - 1]}', ${i}='${words[i]}'`,
      );
    }
  }
}

async function loadTrieCtor() {
  let mod;
  try {
    mod = await import("dawg-lookup/lib/trie");
  } catch {
    mod = await import("dawg-lookup/lib/trie.js");
  }
  const Trie = mod.Trie ?? mod.default?.Trie ?? mod.default;
  if (!Trie) {
    throw new Error("Unable to resolve Trie constructor from dawg-lookup/lib/trie.");
  }
  return Trie;
}

export async function buildPackedDawg(words) {
  const Trie = await loadTrieCtor();
  const trie = new Trie();
  if (typeof trie.addWords === "function") {
    trie.addWords(words);
  } else if (typeof trie.insert === "function") {
    for (const word of words) {
      trie.insert(word);
    }
  } else {
    throw new Error("Trie implementation does not expose addWords() or insert().");
  }
  const packed = trie.pack();
  if (typeof packed !== "string") {
    throw new Error("Expected trie.pack() to return a string payload.");
  }
  return packed;
}

async function readJson(pathname) {
  try {
    const raw = await fs.readFile(pathname, "utf8");
    return JSON.parse(raw);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return {};
    }
    throw error;
  }
}

async function writeMeta({ dawgBytes, dawgSha256 }) {
  const meta = await readJson(META_PATH);
  meta.artifacts = {
    ...(meta.artifacts ?? {}),
    dawgFile: DAWG_FILE_NAME,
    dawgBytes,
    dawgSha256,
  };
  await fs.mkdir(path.dirname(META_PATH), { recursive: true });
  await fs.writeFile(META_PATH, `${JSON.stringify(meta, null, 2)}\n`, "utf8");
}

async function copyDawgLookupLicense() {
  const candidates = [
    path.join(ROOT, "node_modules", "dawg-lookup", "LICENSE"),
    path.join(ROOT, "node_modules", "dawg-lookup", "LICENSE.md"),
  ];
  let source = null;
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      source = candidate;
      break;
    } catch {
      // Try next candidate.
    }
  }

  if (!source) {
    throw new Error(
      "Could not find dawg-lookup LICENSE in node_modules. Run npm install before dict:dawg.",
    );
  }

  await fs.mkdir(LICENSES_DIR, { recursive: true });
  await fs.copyFile(source, DAWG_LICENSE_DEST);
}

export async function buildDawgFromWordsFile() {
  const progress = new ProgressTracker(5);

  let stepStarted = progress.start("Read + validate words.txt");
  const wordsText = await fs.readFile(WORDS_PATH, "utf8");
  const words = parseWordsFile(wordsText);
  assertSortedUnique(words);
  progress.done(stepStarted, `${words.length} words`);

  stepStarted = progress.start(
    "Build packed DAWG",
    "This is CPU-bound and can take a while on larger dictionaries.",
  );
  const packed = await buildPackedDawg(words);
  progress.done(stepStarted, `${Buffer.byteLength(packed, "utf8")} bytes packed`);

  stepStarted = progress.start("Write dict.dawg artifact");
  await fs.mkdir(path.dirname(OUT_PATH), { recursive: true });
  await fs.writeFile(OUT_PATH, packed, "utf8");
  progress.done(stepStarted, OUT_PATH);

  const dawgBytes = Buffer.byteLength(packed, "utf8");
  const dawgSha256 = sha256Hex(packed);
  stepStarted = progress.start("Copy DAWG library license");
  await copyDawgLookupLicense();
  progress.done(stepStarted, DAWG_LICENSE_DEST);

  stepStarted = progress.start("Update dict.meta.json");
  await writeMeta({ dawgBytes, dawgSha256 });
  progress.done(stepStarted, META_PATH);
  progress.summary();

  return { wordsCount: words.length, dawgBytes, dawgSha256 };
}

async function main() {
  const result = await buildDawgFromWordsFile();
  console.log(`Wrote ${OUT_PATH} (${result.dawgBytes} bytes)`);
  console.log(`Words packed: ${result.wordsCount}`);
  console.log(`SHA256: ${result.dawgSha256}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}
