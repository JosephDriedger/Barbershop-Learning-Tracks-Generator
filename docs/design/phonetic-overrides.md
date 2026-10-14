# Design and compatibility assessment: user-approved phonetic overrides

Written in M18. **A design, not an implementation.** It answers: can a singer who is stopped by "BLT does not know how to pronounce this word" give BLT the pronunciation themselves,
through the existing lyric-review workflow, without BLT ever changing the lyrics the score provides? Short answer: **yes, with a small, contained change; no editor is needed.** It is recommended as the
next milestone and is **not** a condition of the release candidate (the respelling route below works today).

## 1. What exists today

| Piece | Fact (checked in this repository and in the pinned OpenUtau) |
|---|---|
| The block | M18: when the dictionary lacks a word, the host stops (exit 11) and BLT reports each word with voice, bar and beat (`core/rendering/pronunciation.py`); nothing is rendered |
| The way out today | **Respell the word in the score** with words the dictionary knows (`every` for `ev'ry`), save, load again. BLT never changes the score's own words (`PLAN_APPROVAL_OVERRIDES_SCORE`). The fixture `docs/acceptance/fixtures` shows the three states (known / unknown / respelled) |
| OpenUtau's own mechanism | a note's lyric may carry its pronunciation: `ev'ry[eh v r iy]`. OpenUtau splits it (`phoneticHintPattern = \[(.*)\]`, `UNote.ToPhonemizerNote`): the phonemizer receives the lyric `ev'ry` and the hint `eh v r iy`, and does **not** look the word up. The M18 host tests prove this for Arpasing, English VCCV and X-SAMPA |
| What the hint is made of | **the phonemizer's own symbols**: ARPAbet (`eh v r iy`) for Arpasing and English VCCV, X-SAMPA (`E v r i`) for X-SAMPA. Arpasing silently drops a symbol it does not know (`Where(g2p.IsValidSymbol)`), so a mistyped symbol would shorten the word without any message |
| BLT's USTX writer | refuses a bracket in a lyric (`USTX_LYRIC_TEXT`), by design: it is how a hint would sneak in unreviewed |
| The lyric review | `blt.lyric-review/1` (report) and `blt.lyric-approvals/1` (what a person writes back, bound to the score's SHA-256). An approval may only target a note **without** a score lyric; a GUI dialog edits the same data (`ui/lyric_review.py`) |
| Words across notes | since M18 a word on several touching notes is sent whole on its first note (`core/synthesis/openutau/words.py`); a hint therefore belongs on that first note |

## 2. The design

**A pronunciation override is a new, separate kind of approval. It never edits a lyric.**

1. **What it is.** A decision "in this score, the word *W* is pronounced *symbols*", made by a named person, bound to the score's SHA-256 and to a **pronunciation alphabet** (`arpabet` or `xsampa`, taken from the chosen
   phonemizer). Keyed by the word (lower-case, as the host reports it), so one decision covers every voice and every occurrence; an optional narrower key (voice and start) can override it in one place.
2. **Where it is stored.** The approvals file gains an optional second list next to `approvals`:
   `{"schema": "blt.lyric-approvals/1", "source_sha256": "...", "approvals": [...], "pronunciations": [{"word": "ev'ry", "alphabet": "arpabet", "symbols": "eh v r iy", "approved_by": "..."}]}`.
   A reader that does not know `pronunciations` ignores it (the file stays valid for older versions), and the score-hash binding rejects decisions made for another version of the score, exactly as for lyrics.
3. **How it reaches the singer.** The refusal already lists the words. BLT adds `blt.pronunciation-template/1`: the same words with empty `symbols` and the alphabet filled in, written next to the lyric-review
   report. The singer fills in the symbols (a text file; the symbol list for the alphabet is printed in the template header), or, in the GUI, the dialog that shows the refusal gets a *Pronunciations...* button that opens the same
   file in the existing file chooser. No phonetic editor, no playback, no new window.
4. **Where it takes effect.** Only in the plan-to-USTX step (`write_ustx`), and only for the dictionary phonemizers: the first note of each occurrence of *W* gets the lyric `W[symbols]`. The plan's lyric text is unchanged
   (`NoteLyric.text` stays what the score says); the override rides in a new field (`NoteLyric.pronunciation`) so that reports, manifests and the lyric review still show the score's own words. The default
   phonemizer and UTAU-style banks ignore overrides (they sing syllables as aliases), and BLT says so if an override targets one.
5. **Validation, so nothing is dropped silently.** Before writing, BLT checks every symbol against the phonemizer's symbol set. The set comes from the host (`blt-render-host --symbols PHONEMIZER`, answering with the phonemizer's
   own `IsValidSymbol`, voicebank dictionary included), never from a copy in Python. An unknown symbol is an error naming the word and the symbol. A hint with the wrong number of vowels for the notes of the word is reported
   (the syllable phonemizers answer "not enough extension notes" otherwise).
6. **The audit trail.** The manifest of a generated package lists the overrides used (word, alphabet, symbols, who approved), next to the lyric approvals, so a track is always traceable to the words and pronunciations that made it.

## 3. Compatibility assessment

| Question | Assessment |
|---|---|
| Does it change score-provided lyrics? | **No.** The text stays; the override is a separate approval applied only to the project file sent to the engine. The existing guard (a score lyric is never overridden) stays untouched |
| Does it break existing files or the lyric review? | No: `approvals` is unchanged; `pronunciations` is optional; the lyric-review rows (notes without lyrics) are unaffected |
| Does it depend on unreviewed upstream behaviour? | It uses OpenUtau's documented hint syntax, tested here on all three English phonemizers. It adds one host mode (`--symbols`) |
| Does it need a model or new data? | No. It is the opposite of a model: a person's explicit decision |
| What can go wrong? | wrong alphabet for the chosen phonemizer (guarded by the alphabet field); a mistyped symbol (guarded by validation); a hint that does not fit the number of notes (reported); overrides that outlive a score edit (guarded by the hash) |
| Risk to the current release candidate | none if it is built after the candidate: it is additive and the refusal text already tells the singer to respell |
| Size | host `--symbols` (small); `PronunciationApproval` and the file schema (small); plan field and USTX writer (small); template and CLI `--approve-pronunciations` (small); one GUI button (small); tests per phonemizer on the real host (medium). About one milestone |

## 4. Recommendation

* **Not essential for the release candidate**: a singer can always respell in the score, the refusal says exactly how, and nothing is guessed. The English acceptance test exercises that route (fixture `known` / `unknown` / `respelled`).
* **Recommended next**: poetic and dialect forms (`ev'ry`, `heav'n`, `o'er`, `'neath`, `mammy`) are common in this repertoire, and respelling changes the written score. An override lets the score stay as the arranger wrote it.
* **Not recommended**: a phonetic editor with playback, or any automatic suggestion of symbols (it would be a pronunciation model by another name).
