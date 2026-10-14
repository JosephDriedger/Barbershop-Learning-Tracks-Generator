# English voicebank acceptance (a person listens)

Checklist version 1 (M15). Read [README.md](README.md) first. **A result is only valid for the installer whose SHA-256 you write in
section 1.**

What this decides: whether BLT's tracks, made with a real English voicebank from a real barbershop score, are good enough for
singers to learn from: the right notes, understandable words, each part clearly audible when it should be. What it does **not**
decide: licensing, installation on other PCs (that is [clean-machine-verification.md](clean-machine-verification.md)), or other voicebanks.
Until someone has done this and a verdict of *accepted* has been recorded in the release gate, BLT's claim that it produces
intelligible English singing is **unverified**.

## 1. What you record before you start

| | |
|---|---|
| Your name and role (for the record) | |
| Date | |
| Installer file name and **SHA-256** (compare with the one you were sent: `Get-FileHash <file> -Algorithm SHA256` in PowerShell; if it does not match, stop) | |
| Windows version (`winver`) | |
| Headphones or speakers used | |
| Voicebank: name, version, author, where you got it, the licence terms (do not send the voicebank to anyone) | |
| Score: title, composer/arranger, where you got it, licence (use an original or public-domain arrangement; do not send copyrighted scores) | |
| Score size: number of measures, tempo(s) | |

## 2. Choose a voicebank and a pronunciation engine that fit

BLT only makes the notes and words; **the voicebank must understand them.** Read the voicebank's readme (or its page) and find which
way it is built. BLT's host supports these English engines (type the full name into *Advanced > Pronunciation engine*; leave it blank
for banks whose sounds are named like the lyrics):

| The bank is built as | Pronunciation engine to type |
|---|---|
| plain syllables that match the lyrics (`la`, `ba`, ...), or you are unsure | *(blank: the default `OpenUtau.Core.DefaultPhonemizer`)* |
| "ARPAsing" (ARPAbet phonemes such as `k ae t`) | `OpenUtau.Plugin.Builtin.ArpasingPhonemizer` |
| English VCCV | `OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer` |
| English X-SAMPA | `OpenUtau.Plugin.Builtin.EnXSampaPhonemizer` |

**Not available in this build:** the "Arpasing+" and "English C+V" engines (removed for licensing reasons, see
`docs/g2p-plus-provenance.md`). A bank that *only* works with those cannot be accepted with this release; say so in the results and stop.
Neural renderers are not part of this build; leave *Rendering engine* blank (WORLDLINE-R).

If you try an engine and the program says it cannot find it ("did not resolve"), that is a result: write the exact message down.

## 3. The score

A four-part TTBB (Tenor, Lead, Baritone, Bass) arrangement exported from MuseScore as MusicXML (`.musicxml`, `.xml` or `.mxl`), with
lyrics typed under the notes. It should contain at least:

* every voice singing at some point, with the Lead carrying the words (the other parts may have no lyrics of their own: BLT then
  uses the Lead's words, as is usual in barbershop);
* one **melisma or slur** (one syllable held over several notes);
* one place where the parts **enter at different times**;
* a tempo that is **not 120**;
* **two or three words that an English dictionary may lack**, the kind old songs have: `ev'ry`, `heav'n`, `o'er`, `'neath`, `mammy` (BLT's pronunciation dictionary is CMUdict, which lacks these; what happens to them depends on the build, see step 10b);
* ordinary barbershop ranges (Bass low, Tenor high).

## 4. Steps

Mark each step **PASS**, **FAIL** or **COULD NOT RUN**, and write what you saw in "Notes". Number the problems you find (P1, P2, ...) with
the measure number.

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 1 | Install the installer you were given (per-user install, accept the defaults). Start **BLT Music Generator** from the Start menu. | Windows may warn about an unsigned program; you can continue (More info > Run anyway). The window opens. | | |
| 2 | In the *Voices* section, point BLT at the folder that contains your voicebank (or put it in `Documents\OpenUtau\Singers`) and press *Refresh*. | Your voicebank is listed. If not, write the folder you used. | | |
| 3 | *Choose score...* and open your score. | The parts are listed; no error. | | |
| 4 | Assign Tenor, Lead, Baritone, Bass (try *Suggest voices*, then correct it). Choose your voicebank as the singer. If section 2 says so, type the pronunciation engine in *Advanced*. | The assignment is accepted. | | |
| 5 | Open *Review lyrics...* | Notes of parts without lyrics of their own are listed as "Follows the Lead". Nothing you did not expect. Note anything that looks wrong, and anything you could not understand. | | |
| 6 | Choose an output folder and WAV. Press **Generate**. | Stages finish without errors. Note the time it took. | | |
| 7 | *Open output folder*. | A folder with **13 WAV files** and `manifest.json`. List the file names in the Notes. | | |
| 8 | Play the **Full quartet** file all the way through. | All four voices sing; pitches match the score; the song ends where the score ends. | | |
| 9 | Play each part's **Solo** file (Tenor, Lead, Baritone, Bass). | Each is that part alone, with the right notes (check the highest and lowest notes against a keyboard or tuner). | | |
| 10 | For each part, follow the lyrics on paper while you listen to its Solo file. Score intelligibility 1-5 (see section 5). | Write four scores. | | |
| 10b | Listen to the **unusual words** (the ones from section 3). Ask the owner which build you have: *with* the pronunciation model, or *without* it. | *With the model*: each is sung with a plausible pronunciation (note which are wrong; a wrong guess is a finding, not a failure). *Without the model*: generation **stops** with a message that names the word and says it is missing from the pronunciation dictionary; respell the word with ordinary words (`every` for `ev'ry`) in the lyric review and generate again; the respelled version is sung. A track that is silently silent at that word is a FAIL. | | |
| 11 | Listen at the melisma/slur bars. | One vowel is held across the notes; the syllable is not sung again on every note. | | |
| 12 | Listen where the parts enter at different times and where they release. | Entrances and releases line up in the Full quartet; no drift between parts over the whole song. | | |
| 13 | Play each part's **Predominant** file. | That part is clearly the loudest and easy to follow, and the other three are present but quiet. Score 1-5 per part. | | |
| 14 | Play each part's **Without** file. | Exactly the named part is missing and the other three are all there. | | |
| 15 | Technical: open two or three WAVs in a normal player (and in an audio editor if you have one). | They play; no clicks, no clipping (no flat tops in the waveform), similar loudness between files. All 13 files are the same length. | | |
| 16 | Optional (needs an FFmpeg you installed yourself): choose MP3, generate again into a new folder. | MP3 files play and sound like the WAVs. | | |
| 17 | Close BLT, start it again. | Your folders and settings are remembered; a second generation starts quickly. | | |
| 18 | Honest first impressions: could you have done steps 2 to 7 **without help**? Where did you hesitate, and what would you have clicked instead? | | | |

## 5. Scoring guide

| Score | Intelligibility (step 10) | Predominant clarity (step 13) |
|---|---|---|
| 5 | every word understood | the part is easy to follow throughout |
| 4 | one or two words unclear | easy except in a few spots |
| 3 | most words understood, some effort | followable with effort |
| 2 | only some words understood | often lost |
| 1 | not understandable | the part cannot be followed |

**Suggested rule for the verdict** (the tester decides; write your reasons):

* *Accepted*: steps 1-9, 11-15 pass; every intelligibility and clarity score is at least 3 and the average at least 4; no problem
  that would mislead a singer (wrong pitch, wrong word, a missing part).
* *Accepted with known issues*: all of the above except some scores of 3 or minor problems that you list. The owner decides whether to
  accept the issues.
* *Rejected*: any wrong pitches, a part missing or wrong, a track that does not play, intelligibility below 3 for any part, or a crash.
* *Not verified*: you could not complete the steps. Say which step and why.

## 6. Results block (copy into a text file and send it back)

```
BLT ACCEPTANCE RESULT: English voicebank
Checklist version: 2
Tester / role / date:
Installer file and SHA-256:
Windows version:
Voicebank (name, version, author, licence):
Pronunciation engine used:
Build: with / without the pronunciation model (as told by the owner):
Unusual words (list; what you heard, or what BLT said and what you did):
Score (title, source, licence, measures, tempo):
Steps 1-18 (including 10b): PASS / FAIL / COULD NOT RUN with a note for each:
Intelligibility per part (T/L/Bar/Bass, 1-5):
Predominant clarity per part (T/L/Bar/Bass, 1-5):
Problems found (P1.., with measure numbers):
Could you do steps 2-7 without help? What confused you?
VERDICT: accepted / accepted with known issues / rejected / not verified
Reasons:
```
