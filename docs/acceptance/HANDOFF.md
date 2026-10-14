# Release-candidate acceptance: handoff for the external tester

BLT Music Generator turns a four-part barbershop score (MusicXML from MuseScore) into 13 learning tracks. The developers cannot judge whether the
tracks **sound right**, or whether it **installs and uninstalls cleanly on a PC that has never seen it**. You can. About 3-4 hours. This build is
**NOT FOR RELEASE**: do not share it. Do not fix anything yourself; write down what you see. "Could not run" is a valid answer.

## What you receive (the tester kit)

| File | Purpose |
|---|---|
| `BLT-Music-Generator-0.1.0-Setup.exe` | the build under test |
| `BLT-Music-Generator-0.1.1-Setup.exe` | the **same program with a higher number**, only so that you can test *upgrading* |
| `SHA256SUMS.txt` | the checksums. **Compare them with the ones the developer sent you separately** (below) |
| `Collect-Environment.ps1`, `Check-UserData.ps1`, `Check-Outputs.ps1` | three small helper scripts (they change nothing except `Check-UserData`'s clearly named marker files; `Check-Outputs` only reads the 13 tracks and checks with arithmetic that they line up) |
| `scores\` | three tiny English test scores (known words / words the dictionary lacks / the same respelled) and `english-quartet.words.json`, which lists every word. Use them with your voicebank before your own score |
| `HANDOFF.md` (this page), `english-voicebank-acceptance.md`, `clean-machine-verification.md` | the instructions; this page is the short version, the other two have every step and the results blocks |

You bring: a Windows 10/11 **64-bit** PC or VM that has never had BLT or developer tools (a VM snapshot lets you repeat steps); headphones; a legitimately obtained **English
voicebank**; a four-part TTBB MusicXML score with lyrics (original or public domain). No Python, git or Visual Studio is needed or wanted.

**First:** in PowerShell, `Get-FileHash .\BLT-Music-Generator-0.1.0-Setup.exe -Algorithm SHA256` and check it equals the number in the developer's message. If it does not, stop.
Then run `powershell -ExecutionPolicy Bypass -File Collect-Environment.ps1 | Tee-Object environment.txt` and keep `environment.txt`.

## The six checks, in this order

| # | Check | Do this | Full steps |
|---|---|---|---|
| 1 | **Clean install, runtime present** | On a PC that has the Visual C++ runtime (the script says), install 0.1.0 per user, start BLT from the Start menu, run `blt.exe selftest` (also with the network off) | clean-machine **A1-A6** |
| 2 | **Runtime missing** | On a PC/VM *without* the runtime: Install -> a dialog "Microsoft Visual C++ runtime needed" must appear with three buttons. Try: *Go back*; *Download*; *offline file beside the installer*; answering **No** to the Windows permission prompt; a wrong file; no network; a silent install. Record every window and message (screenshots) | clean-machine **B1-B13** |
| 3 | **English singing** | This build has **no pronunciation model**. With your voicebank: (a) generate from the three kit scores: the *known* and *respelled* ones must make 13 tracks, the *unknown* one must **stop and name five words** (`lov'd`, `mammy`, `ev'ry`one, `'neath`, `o'er`) with their voices and bars; (b) run `Check-Outputs.ps1` on each set of tracks; (c) listen to every part's Solo, Predominant and Without file against the pitch, rhythm, synchronisation, pronunciation and mix checklists; (d) repeat with your own score | english-voicebank **steps 1-26** |
| 4 | **Upgrade, data kept** | With 0.1.0 installed and a *real* generated track set: run `Check-UserData.ps1 -Mode Create`, add a text file of your own to the program folder, then run the **0.1.1** installer over it. Run `Check-UserData.ps1 -Mode Verify` | clean-machine **A9** |
| 5 | **Uninstall, data kept** | Settings > Apps > BLT Music Generator > Uninstall. Run `Check-UserData.ps1 -Mode Verify` again; look at what is left in the program folder and in `%LOCALAPPDATA%\BarbershopLearningTracks`. Reinstall: are your settings remembered? | clean-machine **A10** |
| 6 | **Report** | Fill the results sheet below and send it with `environment.txt`, the screenshots and your notes | |

What you should see in 4 and 5: **KEPT** for every line of `Check-UserData` (your voicebanks, your generated tracks, your settings); the program, its Start-menu entry and its private
working copy are removed on uninstall; a file you added to the program folder is left behind (it is yours). Anything **LOST** is a serious defect: write down the step.

## What the developers most want to know

* Was every message understandable to someone who is not technical (especially in check 2)?
* Does the English singing sound like the words? (check 3: the verdict that decides whether BLT can be released)
* Did anything touch your computer beyond what the instructions describe, or contact the network when it should not (only check 2, "Download", should)?

## Results sheet (copy, fill, send)

```
BLT ACCEPTANCE RESULT: handoff sheet (checklist version 2)
Tester / date:
Installer 0.1.0 SHA-256 (as you computed it):          matches the developer's number: yes / no
Machine(s): (attach environment.txt for each)
1 Clean install, runtime present:          PASS / FAIL / COULD NOT RUN   notes:
2 Runtime missing (list B1-B13 separately): PASS / FAIL / COULD NOT RUN   notes:
3 English singing: verdict accepted / accepted with known issues / rejected / not verified
   (kit scores: the unknown-words score stopped at exactly the five words: yes / no; Check-Outputs.ps1 on the known and respelled sets: PASS / FAIL)
   intelligibility T/L/Bar/Bass (1-5):          predominant clarity T/L/Bar/Bass (1-5):
   voicebank (name, version, licence):          score (title, source, licence):
4 Upgrade 0.1.0 -> 0.1.1, data KEPT / LOST:     notes:
5 Uninstall, data KEPT / LOST; left behind:      reinstall remembered settings: yes / no
Unclear messages (quote them):
Problems found (P1.., with check and step number):
Overall: accepted / accepted with known issues / rejected / not verified
```

The developer files your sheet as evidence in the release gate (`docs/release-gate.md`): your name, the installer's SHA-256 and your results are what a release decision is built on.
