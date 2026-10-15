# Pronunciation overrides: design, and what M19 built

Designed in M18 (an assessment, nothing built), **implemented in M19**. This page keeps the design and says, in section 6, where the implementation differs from it and what it does not do. Short version: a singer who is stopped
by "BLT does not know how to pronounce this word" can say how that word is pronounced **at that place of that score, for that voice**, in the notation of the chosen pronunciation engine, in the GUI or in a file; the
score's own lyrics are never changed, the engine itself checks the decision before anything is rendered, and the package records the score's words and the decision side by side.

## 1. What exists

| Piece | Fact (checked in this repository and in the pinned OpenUtau) |
|---|---|
| The block | when the dictionary lacks a word, the host stops (exit 11) and BLT reports each word with voice, bar and beat (`core/rendering/pronunciation.py`); nothing is rendered |
| OpenUtau's mechanism | a note's lyric may carry its pronunciation: `ev'ry[eh v r iy]`. OpenUtau splits it (`phoneticHintPattern = \[(.*)\]`, `UNote.ToPhonemizerNote`): the phonemizer receives the lyric `ev'ry` and the hint `eh v r iy`, and does **not** look the word up |
| What the hint is made of | the phonemizer's own symbols. **Arpasing**: ARPAbet from its g2p (`IsValidSymbol`), and it **drops** a symbol it does not know without a word. **English VCCV** and **X-SAMPA**: the hint is taken **as written**; the engine's own symbols (VCCV `E`, `@`, `9`...; X-SAMPA `E`, `{`, `I\`...) and also ARPAbet, which the two engines translate with the same table they apply to the dictionary (so `eh v r iy` and `E v r i` give the same sounds) |
| BLT's USTX writer | still refuses a bracket in a **score** lyric (`USTX_LYRIC_TEXT`): that is how a hint would sneak in unreviewed. A decided pronunciation is the one exception, written only from a validated, scoped override |
| The lyric review | unchanged. `blt.lyric-approvals/1` still only approves notes that have no score lyric. Pronunciations are a **separate** kind of decision with a separate file |

## 2. The design as built

**A pronunciation override is a person's decision about one word at one place of one score. It never edits a lyric.**

1. **Scope: all four are part of the decision.**
   * *the score*: the SHA-256 of the MusicXML file (`source_sha256`); a decision for another version is refused as a whole;
   * *the voice and the place*: `voice` and `start` (quarter notes), the first note of the word as the engine receives it; the same word in another bar, or in another voice, is **not** affected and needs its own decision;
   * *the word*: the text the engine receives for that note (the score's syllables put together: `ev'` + `ry` + `one` is `ev'ryone`). A decision made for another word than the score now has there is refused (stale);
   * *the engine*: the fully qualified phonemizer the symbols were written for. The notation of one engine is refused for another.
2. **Where it is stored.** `blt.pronunciation-overrides/1` (`core/pipeline/pronunciation_files.py`): `{"schema", "source_sha256", "overrides": [{"voice", "start", "where", "word", "phonemizer", "notation", "symbols", "approved_by"}]}`.
   `where` and `notation` are for the reader. A stopped run writes a **template** (one entry per blocked voice and place, `symbols: null`); an undecided entry decides nothing (the word stays blocked). In the GUI the same data lives in memory for the session and is saved and loaded with
   *Save pronunciations* and *Load pronunciations*, exactly like the lyric approvals.
3. **How it reaches the singer.** A stopped run (GUI: the message, with an *Open Pronunciations* button and a *File > Pronunciations* entry; CLI: the template written next to the output and the line "rerun with `--approve-pronunciations FILE`") lists every place: voice, bar and beat, the score's own text,
   the word sent to the engine and the engine. The dialog says which notation each engine takes and shows it in a tooltip. Nothing is filled in. *Same for the other voices here* copies a decision only to the other voices at the same note and word, only when clicked.
4. **Where it takes effect.** Only in the project file sent to the engine (`write_ustx`), and only for the three dictionary phonemizers: the first note of the word is written `word[sym bol s]`. The plan (`NoteLyric.text`, `provenance.source_text`), the lyric review and the package keep the score's own text.
5. **Validation, before anything renders.**
   * *form* (Python): at least one symbol, at most 64, no brackets, spaces inside a symbol or control characters; an `approved_by`; the score's SHA-256;
   * *fit* (Python, `resolve_overrides`): the score, the voice, a note that starts there, the first note of a word the engine receives, the same word, the engine of that voice, no second decision for one note. Anything else is an error that says why (`OVERRIDE_WRONG_SCORE`, `OVERRIDE_NO_NOTE`, `OVERRIDE_WORD_MISMATCH`, `OVERRIDE_PHONEMIZER_MISMATCH`, `OVERRIDE_NOT_WORD_START`, `OVERRIDE_DUPLICATE`...). Nothing is skipped;
   * *symbols* (the engine itself): the patched phonemizers record every hint symbol they do not know (`HintProblems`); the host stops with exit 12 (`pronunciation_invalid`) naming the voice, the bar and the symbol, **before** any stem is rendered; a hinted note that makes no sound, or on which the engine threw an
     exception, is refused too. The symbol list is never copied into Python: it is whatever the engine accepts, including a voicebank's own dictionary.
   * *dry run*: `blt-render-host --phonemize-only` (BLT: `check_pronunciations`, GUI: *Check with the engine*) does everything up to and including that check and stops: no stem, no package, a few seconds.
6. **The audit trail.** `manifest.json` has a `pronunciation` section: the dictionary used, and one record per decision: voice, start, bar and beat, the word, **the score's own text** (`score_lyrics`: `["ev'", "ry", "one"]`), the engine, the notation, the symbols as written, who decided, the score's SHA-256, the scope, and
   **the sounds the engine made of it** (`effective_phonemes`, from the engine). With no decisions the list is empty and the manifest says the dictionary alone was used.

## 3. Compatibility assessment (as it turned out)

| Question | Result |
|---|---|
| Does it change score-provided lyrics? | No. The score file is byte-identical after a run (tested); the plan and the review keep the score's text; the decision is applied only to the project sent to the engine |
| Does it break existing files or the lyric review? | No: `blt.lyric-approvals/1` is untouched; the manifest gained a section (`pronunciation`), no key was removed |
| Does it depend on unreviewed upstream behaviour? | It uses OpenUtau's hint syntax, tested on all three engines with the real host, and adds to the existing always-applied patch (`HintProblems` beside `MissingWords`) and two host options |
| Does it need a model or new data? | No: it is a person's explicit decision, the opposite of a model |
| What can go wrong | a wrong notation for the engine (refused: symbols the engine does not know are named); symbols that are valid but wrong for the word (BLT cannot know: the person listens, the checklist says how); a decision outliving a score edit (refused by the hash, and by the word check) |

## 4. Limits, stated

* **Bound to the whole score.** Any change of the MusicXML file, even one that has nothing to do with the word, makes the saved decisions invalid; they must be decided again (a new template is written by the next stopped run). This is the same rule as the lyric approvals and is deliberate: BLT cannot
  tell which edits matter. A finer binding is possible later (keep a decision when the voice, place and word still match); it was not done because a decision that follows an edited score silently is the very thing this feature must not do.
* **One engine per decision.** A decision for Arpasing is not used when the voice uses X-SAMPA. The notation help names the notation; ARPAbet is accepted by all three engines.
* **Vowel-initial words with English VCCV are unverified.** With the synthetic test voicebank the engine throws on words that begin with a vowel (OpenUtau answers with the alias `error`), with or without a pronunciation. BLT now names that ("the pronunciation engine failed on...") instead of blaming the voicebank,
  and a hinted note on which the engine failed is refused. Whether a real English VCCV bank has the same trouble needs a real bank; it is in the acceptance checklist.
* **A word on fewer notes than it has vowels.** The syllable engines then report that there are not enough extension notes; Arpasing squeezes the sounds into the notes it has. A pronunciation does not change how many notes the voice has.
* **A fragment** (a syllable of a longer word that a follower voice sings alone, see `docs/m19-report.md`) can be given a pronunciation like any word: it is the word the engine receives for that note.
* **Words built from the dictionary (added after M19, at the user's request).** A word the dictionary lacks is no longer always a stop. For the three dictionary engines (Arpasing, English VCCV, X-SAMPA; each takes ARPAbet in a hint) the backend (`core/rendering/compose.py`, used by `backend.py`) reads the word as a spelling of a dictionary word (an apostrophe for a left-out letter, `in` for `ing`, `Oo` for `ooh`) or cuts it into a few dictionary words and joins their sounds. It
  only ever uses entries the dictionary has (asked through the host's `--lookup-words`), never a model and never letter-to-sound rules, and what it cannot cover stays a stop. The result is sent as an ordinary phonetic hint for that one note; it is recorded (`pronunciation.overrides[*]`: `source: "composed"`, `composed_from`, `composed_how`, `approved_by: null`) and
  warned about (`PRONUNCIATION_COMPOSED`), so it is never taken for a person's decision, and a person's own decision for that note always wins. It is a spelling-based reading, not proof of the right sound: `--no-composed-pronunciations` restores the stop for every word.
  BLT still does not play anything back; the person listens.

## 5. Recommendation (unchanged)

The model-free release is usable for the repertoire's old-fashioned words (`ev'ry`, `o'er`, `'neath`, `mammy`, `lov'd`) without changing the score. What remains uncertain is how it **sounds** with real voicebanks, which only the acceptance listening test can say.

## 6. Where the implementation differs from the M18 design

| M18 design | M19 |
|---|---|
| a second list `pronunciations` in the lyric-approvals file | **a separate file** (`blt.pronunciation-overrides/1`): simpler to read and write, nothing for the older reader to ignore |
| keyed by word, one decision for every occurrence, an optional narrower key | **always** per voice and note: the decision's scope is the occurrence; a convenient "same for the other voices here" action exists but only copies to the same note and word |
| symbols validated by a new host mode `--symbols` answering `IsValidSymbol` | the engines **record** the symbols they do not know while phonemizing the real project (a single code path, including a voicebank's own dictionary), plus `--phonemize-only` as the dry run |
| alphabet field per entry | the engine decides what it accepts; `notation` is help text and the manifest records the engine and the notation name |
| a *Pronunciations...* button in the existing review | a dialog of its own (the lyric review lists notes without lyrics; these are words that have lyrics), opened from the failure message and from the File menu |
