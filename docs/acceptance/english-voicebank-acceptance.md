# English voicebank acceptance (a person listens)

Checklist version 4 (M19). Read [README.md](README.md) first. **A result is only valid for the installer whose SHA-256 you write in
section 1.**

What this decides: whether BLT's tracks, made with a real English voicebank, are good enough for singers to learn from: the right notes,
understandable words, each part clearly audible when it should be, every mix what its name says. What it does **not** decide: licensing,
installation on other PCs (that is [clean-machine-verification.md](clean-machine-verification.md)), or other voicebanks. Until someone has
done this and a verdict of *accepted* has been recorded in the release gate, BLT's claim that it produces intelligible English singing is
**unverified**.

**About this build.** It has **no pronunciation model**. English words are looked up in a dictionary (CMUdict). A word the dictionary does not
have is **never guessed**: BLT stops before it renders anything and tells you the word, the voice and the bar. There are two cures, and this test
exercises both with scores that come in the kit: **respell** the word in the score with ordinary words (`every` for `ev'ry`), or **say how that
word is pronounced** at that place (File > Pronunciations, or a file) without changing the score at all. BLT never guesses the pronunciation and
never changes the words of your score.

## How the test is organised

| Part | What you do | Needs | About |
|---|---|---|---|
| **A. Pronunciation** (steps 1-9h) | install; make tracks from the three **kit scores** with the fixed test voices; confirm BLT stops where it must and sings where it may; then give the pronunciations yourself (9d-9h) | the kit's `scores\` folder and your voicebank | 60 min |
| **B. The arithmetic check** (step 10) | run `Check-Outputs.ps1` on the folder BLT made. It proves, with numbers, that the 13 files line up and that every mix contains what it should. | PowerShell | 5 min |
| **C. Listening** (steps 11-24) | the checklists for pitch, rhythm, synchronisation, pronunciation, predominant mixes, solos and minus-one mixes | headphones, the same output | 90 min |
| **D. Your own score** (step 25) | optional but wanted: the same on a real arrangement of your own | an original or public-domain score | 60 min |

The numbers of part B do not replace listening: they say that the tracks are *consistent*; only you can say they sound *right*.

## 1. What you record before you start

| | |
|---|---|
| Your name and role (for the record) | |
| Date | |
| Installer file name and **SHA-256** (compare with the one you were sent: `Get-FileHash <file> -Algorithm SHA256` in PowerShell; if it does not match, stop) | |
| Windows version (`winver`) | |
| Headphones or speakers used | |
| Voicebank: name, version, author, where you got it, the licence terms (do not send the voicebank to anyone) | |
| Is the voicebank built for ARPAbet ("ARPAsing"), English VCCV, English X-SAMPA, or plain syllables? (section 2) | |
| Pronunciation engine you typed (or blank) | |

## 2. Choose a voicebank and a pronunciation engine that fit

BLT only makes the notes and words; **the voicebank must understand them.** Read the voicebank's readme (or its page) and find which
way it is built. BLT's host supports these English engines (type the full name into *Advanced > Pronunciation engine*; leave it blank
for banks whose sounds are named like the lyrics):

| The bank is built as | Pronunciation engine to type | Unknown dictionary word |
|---|---|---|
| plain syllables that match the lyrics (`la`, `ba`, ...), or you are unsure | *(blank: the default `OpenUtau.Core.DefaultPhonemizer`)* | not looked up: the syllable is the sound. A syllable the bank lacks is reported afterwards as silent notes |
| "ARPAsing" (ARPAbet phonemes such as `k ae t`) | `OpenUtau.Plugin.Builtin.ArpasingPhonemizer` | **BLT stops and names the word** |
| English VCCV | `OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer` | **BLT stops and names the word** |
| English X-SAMPA | `OpenUtau.Plugin.Builtin.EnXSampaPhonemizer` | **BLT stops and names the word** |

**Not available in this build:** the "Arpasing+" and "English C+V" engines (removed for licensing reasons, see
`docs/g2p-plus-provenance.md`). A bank that *only* works with those cannot be accepted with this release; say so in the results and stop.
Neural renderers are not part of this build; leave *Rendering engine* blank (WORLDLINE-R).

If you try an engine and the program says it cannot find it ("did not resolve"), that is a result: write the exact message down.

**If your bank is built for a dictionary engine (ARPAsing, VCCV or X-SAMPA), run all of part A. If it is plain syllables, run steps 1-8 and 11 onward;
steps 9a-9c do not apply (nothing is looked up), and say so.**

## 3. The three kit scores (part A) and your own score (part D)

The kit's `scores\` folder holds one tiny four-part piece (8 bars, 4/4, 88 beats per minute) in three versions. `english-quartet.words.json`
lists every word, where it is, and whether the dictionary has it. Do not edit the files.

| File | What it is | What BLT must do |
|---|---|---|
| `english-quartet-known-words.musicxml` | ordinary words, contractions (`don't`, `we'll`, `I'm`), an apostrophe at the start (`'cause`), a word over several notes (`together`), a melisma (`sing`), long notes (`know`, `round`, `home`) | make the 13 tracks |
| `english-quartet-unknown-words.musicxml` | the same, with five words that CMUdict lacks: `lov'd` (bar 1, beat 1), `mammy` (bar 2, beat 4), `ev'ryone` (bar 4, beat 1), `'neath` (bar 6, beat 3), `o'er` (bar 7, beat 1) | **stop** before making any track, and name those words with their voices and bars |
| `english-quartet-respelled-words.musicxml` | the unknown version with those words respelled: `loved`, `mommy`, `everyone`, `beneath`, `over` | make the 13 tracks |
| `english-quartet-unknown-words.pronunciations-arpasing.json` (also `-vccv` and `-xsampa`) | **sample pronunciations** for the five places of the unknown score, one file per pronunciation engine; they are tied to that exact score file and to that engine | make the 13 tracks from the *unknown* score, which stays exactly as it is |

For your own score (part D): a four-part TTBB arrangement exported from MuseScore as MusicXML (`.musicxml`, `.xml` or `.mxl`), lyrics under the notes, with
the Lead carrying the words (the other parts may have none of their own: BLT then uses the Lead's words, as is usual in barbershop). It should have
one melisma or slur, an entrance at different times, a tempo that is not 120, and ordinary barbershop ranges. Use an original or public-domain arrangement.
If it holds old-fashioned words (`ev'ry`, `heav'n`, `o'er`) BLT may stop and name them: that is part of the result.

## 4. Steps

Mark each step **PASS**, **FAIL** or **COULD NOT RUN**, and write what you saw in "Notes". Number the problems you find (P1, P2, ...) with the bar number.

### Part A. Install and pronunciation

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 1 | Install the installer you were given (per-user install, accept the defaults). Start **BLT Music Generator** from the Start menu. | Windows may warn about an unsigned program; you can continue (More info > Run anyway). The window opens. | | |
| 2 | In the *Voices* section, point BLT at the folder that contains your voicebank (or put it in `Documents\OpenUtau\Singers`) and press *Refresh*. | Your voicebank is listed. If not, write the folder you used. | | |
| 3 | *Choose score...* and open `english-quartet-known-words.musicxml`. Assign Tenor, Lead, Baritone, Bass (try *Suggest voices*, then correct it). Choose your voicebank as the singer. If section 2 says so, type the pronunciation engine in *Advanced*. | The parts are listed; the assignment is accepted. | | |
| 4 | Open *Review lyrics...* | Notes of parts without lyrics of their own are listed as "Follows the Lead". Nothing you did not expect. Note anything that looks wrong, and anything you could not understand. | | |
| 5 | Choose an output folder and WAV. Press **Generate**. Note the time it took. | Stages finish without errors. | | |
| 6 | *Open output folder*. | A folder with **13 WAV files** and `manifest.json`. List the file names in the Notes. Keep this folder: it is the *known* set. | | |
| 7 | Open `english-quartet-unknown-words.musicxml` instead (same assignment). Press **Generate**. | Dictionary engines: generation **stops** with a message that says BLT does not know how to pronounce some words, and lists them: `lov'd` (bar 1, beat 1), `mammy` (bar 2, beat 4), `ev'ryone` (bar 4, beat 1), `'neath` (bar 6, beat 3), `o'er` (bar 7, beat 1), each with its voices (Tenor, Lead, Baritone, Bass). **No** 13 files are written. Write the message down word for word. Plain-syllable bank: no stop is expected; say what happened. | | |
| 8 | Open `english-quartet-respelled-words.musicxml` (same assignment). Press **Generate** into a new folder. | 13 tracks. Keep this folder: it is the *respelled* set. | | |
| 9a | Dictionary engines: of the words in step 7 which one was **not** listed, or which was listed that is **not** in the table of section 3? | The five words and no other. A word BLT should have stopped at and did not is a **FAIL** (note the word). | | |
| 9b | In the *respelled* set listen to the five respelled words (`loved`, `mommy`, `everyone`, `beneath`, `over`, bars as in the table). | Each is sung as the word it is spelled as. A silent word is a FAIL. | | |
| 9c | In the *known* set listen to `don't`, `we'll`, `I'm`, `'cause`, and `together` (one word over three notes). | Each is a single word, not two or three separate syllables. | | |
| 9d | Open `english-quartet-unknown-words.musicxml` again (same assignment) and press **Generate**: it stops (step 7). Press **Open Pronunciations** in the message (or **File > Pronunciations…**). Write down the **SHA-256 of the score file** first (`Get-FileHash <file> -Algorithm SHA256`). | A table of **17 places**: four voices at each of `lov'd`, `ev'ryone`, `'neath`, `o'er`, and the Bass alone at `mammy`. Each row has the voice, the bar and beat, **the score's own text** (for `ev'ryone`: `ev' · ry · one`), the word sent to the engine and the engine. **Every row says "Needs a pronunciation": nothing is filled in.** Generate is still not possible. | | |
| 9e | In the dialog press **Load pronunciations…** and choose the sample file **for your engine** (arpasing / vccv / xsampa). Type your own name into **Decided by**. Press **Check with the engine**. (Command line: `generate ... --approve-pronunciations <file>`.) | All 17 rows say "Decided", then, after the check, "accepted; the engine sings: ..." with the sounds. A message says the engine accepts them and that nothing was rendered. If a row says it cannot be used, write down the row and the message word for word. (With English VCCV the engine may report that it failed on `ev'ryone`, a word that starts with a vowel: that is a known open question for that engine; write down the message.) | | |
| 9f | Press **Done**, then **Generate** into a new folder. Run `Check-Outputs.ps1` on it (step 10). Keep this folder: it is the *pronunciation* set. | 13 tracks; the arithmetic check passes. `Get-FileHash` of the score file is **the same as before** (the score is never changed). | | |
| 9g | In the pronunciation set listen to the five places and compare with the *respelled* set (`loved`, `mommy`, `everyone`, `beneath`, `over`). | Each word is sung as the sounds of the sample describe it (`lov'd` as *loved*, `ev'ryone` as *everyone* over its three notes in order, `'neath` as *neath*, `o'er` as *ore*, `mammy`). A silent word, a missing syllable or a wrong order is a FAIL. A word that sounds odd although the symbols are right is a **finding about the voicebank**: write down what you heard. | | |
| 9h | Open `manifest.json` of the pronunciation set. Then, in BLT, open Pronunciations again, change one row of `'neath` to a wrong symbol (for example `n zzz th`) and press **Check with the engine**; correct it and check again. Finally open a **different score** and open File > Pronunciations. | `manifest.json` has a `pronunciation` section with 17 records: each keeps the **score's own text** (`score_lyrics`), the word, the engine, the symbols, **your name**, the score's SHA-256 (the one you wrote down) and the sounds the engine made. The wrong symbol is **refused naming the symbol, the voice and the bar**, nothing is generated, and the correction is accepted. For the other score the decisions are **gone** (they belong to one score). | | |

### Part B. The arithmetic check

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 10 | In PowerShell, in the kit folder: `powershell -ExecutionPolicy Bypass -File Check-Outputs.ps1 -Folder "<the known set>" -Report known-check.txt`. Repeat for the respelled set (`respelled-check.txt`) and the pronunciation set (`pronunciation-check.txt`). | The last line says every arithmetic check passed; no line says FAIL; all 13 files have the same length. A FAIL names the voice and the check: do not listen further to that set, send the report. | | |

### Part C. Listening checklists

Use the **known** set unless a step says otherwise. Use headphones. Play each file at least twice.

**Pitch**

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 11 | Play the **Full quartet** all the way through. | All four voices sing; the piece ends where the score ends; parallel thirds and octaves of the test piece are in tune with each other. | | |
| 12 | Play each part's **Solo** file (Tenor, Lead, Baritone, Bass). Check the highest and lowest notes against a keyboard or tuner. | Each is that part alone, with the right notes. Write any wrong pitch with its bar. | | |

**Rhythm and synchronisation**

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 13 | Tap the beat (88 per minute) against the Full quartet; listen at the half notes and the whole note on `home`. | Note lengths match the score; long notes are held their full length and end together. | | |
| 14 | Listen where the melisma is (`sing`, bar 2) in each Solo. | One vowel is held across the notes; the syllable is not sung again on every note. | | |
| 15 | Listen where the parts start and where they release (bars 1, 3, 4, 8). Play two Solo files together in an audio editor if you have one (start both at 0:00). | Entrances and releases line up; no drift between parts over the whole piece; no part starts early or late. | | |

**Pronunciation and intelligibility**

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 16 | For each part, follow the words on paper while you listen to its Solo. Score intelligibility 1-5 (section 5). | Write four scores. A word that is silent, missing, or sung as a different word is a problem (P#), with its bar. | | |
| 17 | Where a word is held over several notes (`together`, bar 3), listen for the syllables in order. | Each syllable once, in order, on the right notes. | | |

**Predominant, solo and minus-one mixes**

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 18 | Play each part's **Predominant** file. Score 1-5 per part (section 5). | That part is clearly the loudest and easy to follow; the other three are present but quiet. | | |
| 19 | Play each part's **Solo** file again, now only for level. | The part alone, same loudness as the other Solos (within a few dB), not silent anywhere it sings. | | |
| 20 | Play each part's **Without** (minus-one) file. | Exactly the named part is missing; the other three are all there, all the way through. Try to sing the missing part with it: can you hear your pitch from the others? | | |
| 21 | Compare the Full quartet with the Without file of one part, then with that part's Solo. | Full sounds like Solo plus Without together. | | |

**Files, program and your impressions**

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 22 | Technical: open two or three WAVs in a normal player (and in an audio editor if you have one). | They play; no clicks, no clipping (no flat tops in the waveform), similar loudness between files. All 13 files are the same length. | | |
| 23 | Optional (needs an FFmpeg you installed yourself): choose MP3, generate again into a new folder. | MP3 files play and sound like the WAVs. | | |
| 24 | Close BLT, start it again. | Your folders and settings are remembered; a second generation starts quickly. | | |

### Part D. Your own score

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| 25 | Repeat steps 3-6, 10 and 11-22 with your own score. If BLT stops at words, either give their pronunciations (File > Pronunciations, one decision per voice and place; **Same for the other voices here** copies a decision to the voices that sing the same word at that place) or respell them in the score as the message says (BLT never changes your score itself). | Same expectations. Record the words it stopped at, which route you took, the symbols you wrote and whether the engine accepted them. | | |
| 26 | Honest first impressions: could you have done steps 2 to 6 **without help**? Where did you hesitate, and what would you have clicked instead? Was the message at a word BLT did not know clear enough to act on? | | | |

## 5. Scoring guide

| Score | Intelligibility (step 16) | Predominant clarity (step 18) |
|---|---|---|
| 5 | every word understood | the part is easy to follow throughout |
| 4 | one or two words unclear | easy except in a few spots |
| 3 | most words understood, some effort | followable with effort |
| 2 | only some words understood | often lost |
| 1 | not understandable | the part cannot be followed |

**Suggested rule for the verdict** (the tester decides; write your reasons):

* *Accepted*: steps 1-6, 8-22 pass (including 9a-9h), **step 7 stops exactly as expected (dictionary engines)**; step 10 passes for all three sets; every intelligibility and clarity score is at least 3 and the
  average at least 4; no problem that would mislead a singer (wrong pitch, wrong word, a missing part).
* *Accepted with known issues*: all of the above except some scores of 3 or minor problems that you list. The owner decides whether to accept the issues.
* *Rejected*: any wrong pitches, a part missing or wrong, a track that does not play, **a word BLT should have stopped at and instead was sung wrongly or silently**, a failed arithmetic check
  with no explanation, intelligibility below 3 for any part, or a crash.
* *Not verified*: you could not complete the steps. Say which step and why.

## 6. Results block (copy into a text file and send it back)

```
BLT ACCEPTANCE RESULT: English voicebank
Checklist version: 4
Tester / role / date:
Installer file and SHA-256:
Windows version:
Voicebank (name, version, author, licence):
Voicebank built for (ARPAbet / VCCV / X-SAMPA / plain syllables) and engine typed:
Kit scores: step 7 message, word for word (and which words, voices and bars it named):
Words BLT should have named but did not / named but should not have:
Respelled set: any word silent or wrong (step 9b):
Contractions and multi-note words (step 9c, 17):
Check-Outputs.ps1: known set PASS/FAIL, respelled set PASS/FAIL, pronunciation set PASS/FAIL (attach known-check.txt, respelled-check.txt, pronunciation-check.txt):
Own score (title, source, licence, measures, tempo), words BLT stopped at and how you respelled them:
Pronunciation workflow (9d-9h): the table listed 17 places with the score's own text, nothing filled in: yes / no
Engine used for the sample file, and what "Check with the engine" said (word for word if a row was refused):
What the five places sounded like (9g); the manifest's pronunciation section (9h: 17 records, your name, the score's SHA-256): yes / no
Score file unchanged after the pronunciation run (SHA-256 before / after):
Steps 1-26: PASS / FAIL / COULD NOT RUN with a note for each:
Pitch problems (bar, voice):
Rhythm / synchronisation problems (bar, voices):
Intelligibility per part (T/L/Bar/Bass, 1-5):
Predominant clarity per part (T/L/Bar/Bass, 1-5):
Solos / minus-one mixes: anything missing or in the wrong mix:
Problems found (P1.., with bar numbers):
Could you do steps 2-6 without help? What confused you?
VERDICT: accepted / accepted with known issues / rejected / not verified
Reasons:
```
