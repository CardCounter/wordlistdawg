# wordlistdawg

Offline dictionary build pipeline:

1. `SCOWLv2` source -> normalized uppercase `words.txt`
2. `words.txt` -> packed DAWG `dict.dawg`
3. Browser runtime uses `src/dict.ts` with no backend

## Output files

### `words.txt`

Plain text file with one word per line, sorted alphabetically. Contains ~200k normalized English words (uppercase A-Z only, no hyphens, accents, or apostrophes). Sourced from SCOWL size 80 which covers all standard English words including uncommon ones used in word games like Scrabble.

### `dict.dawg`

Packed DAWG (Directed Acyclic Word Graph) binary built from `words.txt` using the `dawg-lookup` library. This is a compressed trie structure (~392 KB) that supports fast `isWord` and `isPrefix` lookups without loading the full word list into memory. Used by the runtime API in `src/dict.ts`.

### `dict.meta.json`

Metadata about the source, build profile, word count stats, and DAWG artifact checksums.

## Source profile

- SCOWL source: `https://github.com/en-wl/wordlist` (`v2`)
- Pinned commit: `744c092883db13112f6680892850c1f1b6547b81`
- Size: `80`
- Spellings: `A,B,Z,C,D` (US/UK/CA/AU)
- Classes: core words only (`--poses-to-exclude=abbr`, empty categories/tags)
- Normalization: uppercase, strip non-`A-Z`

## Build commands

```bash
npm install
npm run dict:words
npm run dict:dawg
# or:
npm run dict:build
```

`dict:words` downloads a pinned SCOWLv2 archive. On the first successful download, it records a checksum lock at `data/scowl/source.lock.json`; subsequent runs verify against that checksum.
Both build steps print phase-by-phase progress with elapsed time (for example `[2/7] ... done in 1.2s`) so you can see where time is spent.

## Runtime API

`src/dict.ts` exports:

- `loadDictionary(metaUrl?: string): Promise<void>`
- `normalizeWord(input: string): string`
- `isWord(word: string): boolean`
- `isPrefix(prefix: string): boolean`

## Tests

```bash
npm run dict:test
```

## Attribution

Word list data is derived from SCOWL/SCOWLv2 (`en-wl/wordlist`). Keep the included SCOWL license and copyright notices with distributed dictionary artifacts.
