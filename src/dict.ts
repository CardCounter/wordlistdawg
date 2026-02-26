type DictMeta = {
  artifacts?: {
    dawgFile?: string;
  };
};

type TrieLike = {
  isWord: (word: string) => boolean;
  isPrefix?: (prefix: string) => boolean;
  hasPrefix?: (prefix: string) => boolean;
  completions?: (prefix: string, limit?: number) => string[];
};

let trie: TrieLike | null = null;
let loadPromise: Promise<void> | null = null;

function ensureLoaded(): TrieLike {
  if (!trie) {
    throw new Error("Dictionary not loaded. Call loadDictionary() first.");
  }
  return trie;
}

function resolveAssetUrl(metaUrl: string, dawgFile: string): string {
  if (/^https?:\/\//u.test(dawgFile)) {
    return dawgFile;
  }
  if (typeof window !== "undefined") {
    return new URL(dawgFile, new URL(metaUrl, window.location.href)).toString();
  }
  return dawgFile;
}

async function loadPTrieCtor() {
  let mod: unknown;
  try {
    mod = await import("dawg-lookup/lib/ptrie");
  } catch {
    mod = await import("dawg-lookup/lib/ptrie.js");
  }
  const typedMod = mod as { PTrie?: new (packed: string) => TrieLike; default?: unknown };
  const PTrie = typedMod.PTrie
    ?? (mod as { default?: { PTrie?: new (packed: string) => TrieLike } }).default?.PTrie
    ?? (mod as { default?: new (packed: string) => TrieLike }).default;
  if (!PTrie) {
    throw new Error("Unable to resolve PTrie constructor from dawg-lookup/lib/ptrie.");
  }
  return PTrie;
}

export function normalizeWord(input: string): string {
  return input.toUpperCase().replace(/[^A-Z]/gu, "");
}

export async function loadDictionary(metaUrl = "/dict.meta.json"): Promise<void> {
  if (trie) {
    return;
  }
  if (loadPromise) {
    return loadPromise;
  }

  loadPromise = (async () => {
    const metaResponse = await fetch(metaUrl);
    if (!metaResponse.ok) {
      throw new Error(`Failed to load dictionary metadata from ${metaUrl}: ${metaResponse.status}`);
    }

    const meta = (await metaResponse.json()) as DictMeta;
    const dawgFile = meta.artifacts?.dawgFile ?? "dict.dawg";
    const dawgUrl = resolveAssetUrl(metaUrl, dawgFile);

    const dawgResponse = await fetch(dawgUrl);
    if (!dawgResponse.ok) {
      throw new Error(`Failed to load dictionary data from ${dawgUrl}: ${dawgResponse.status}`);
    }

    const packed = await dawgResponse.text();
    const PTrie = await loadPTrieCtor();
    trie = new PTrie(packed);
  })();

  try {
    await loadPromise;
  } finally {
    loadPromise = null;
  }
}

export function isWord(word: string): boolean {
  const normalized = normalizeWord(word);
  if (!normalized) {
    return false;
  }
  return ensureLoaded().isWord(normalized);
}

export function isPrefix(prefix: string): boolean {
  const normalized = normalizeWord(prefix);
  if (!normalized) {
    return false;
  }

  const loadedTrie = ensureLoaded();
  if (typeof loadedTrie.isPrefix === "function") {
    return loadedTrie.isPrefix(normalized);
  }
  if (typeof loadedTrie.hasPrefix === "function") {
    return loadedTrie.hasPrefix(normalized);
  }
  if (typeof loadedTrie.completions === "function") {
    return loadedTrie.completions(normalized, 1).length > 0;
  }
  throw new Error("Loaded DAWG trie does not expose a prefix lookup method.");
}

export function __resetDictionaryForTests(): void {
  trie = null;
  loadPromise = null;
}
