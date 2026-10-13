# Acceptance tests for a release candidate (to be run by someone other than the developer)

**Short version for the tester: [HANDOFF.md](HANDOFF.md)** (six checks, the helper scripts and a results sheet). `packaging/tester_kit.ps1` (run by `packaging/build.ps1`)
assembles the kit: the installer under test, a second installer of the same program with the next version number for the upgrade check, checksums, these documents and
the helper scripts `Collect-Environment.ps1` and `Check-UserData.ps1`. The pages below are the full steps.

BLT's automated tests prove that the program starts, renders and installs. They cannot prove that it **sounds right**, that it
installs on a PC that has never had a developer tool, or that a normal person can get from a score to 13 tracks. Two
person-run tests close that gap. Both are *required by the release gate* ([../release-gate.md](../release-gate.md)):

| Test | Document | Needs | Time |
|---|---|---|---|
| English voicebank acceptance | [english-voicebank-acceptance.md](english-voicebank-acceptance.md) | the installer, a legitimately obtained English voicebank, a four-part TTBB score, headphones, a Windows PC | 2-3 hours |
| Clean-machine verification | [clean-machine-verification.md](clean-machine-verification.md) | the installer, a Windows 10/11 x64 PC or VM that has never had BLT or developer tools (and, for part B, one that lacks the Visual C++ runtime) | 2-3 hours |

You can do both on the same clean machine in one sitting. Nothing has to be built, no source code is needed, and nobody needs to
run Python or git.

## What the developer gives the tester (the "tester kit")

1. `BLT-Music-Generator-<version>-Setup.exe` and the **SHA-256** of that exact file, written in the message (not only in the folder:
   the number must reach the tester separately from the file).
2. These two documents (PDF or the Markdown files).
3. Optional: `NOTICES.txt` (it is also inside the installer) and a way to send results back (mail, shared folder).

The tester brings: a Windows PC (see each document), a voicebank they obtained and are allowed to use, and a score.

## What the tester sends back

* the filled-in results block at the end of each document (copy it into a text file);
* the files and screenshots the document asks for (the 13 output files do not need to be sent, but keep them);
* the answer to "would you have understood what to do without help?" in your own words.

## How the result becomes part of the release decision

The owner records the tester's result with `python packaging/release_gate.py sign <item> --by "<tester's name>" --role "acceptance tester"
--evidence <path of the result file> --installer-sha256 <sha of the installer tested>` (`english-voicebank-acceptance` or
`clean-machine-verification`). The sign-off is tied to this checklist's exact text and to the installer's SHA-256: if either changes,
the item re-opens. **A tester's "not verified" or "could not run" is a valid result and is recorded as such; it does not close the item.**
Only a person can sign; neither CI nor the developer's tools can.

## Rules for testers

* Do the steps in order and note what **you** saw, not what the document says should happen. A step that surprised you is a result.
* Do not fix problems yourself; write them down with the step number. Do not skip a step you cannot do; mark it "could not run" and say why.
* Do not share the installer or the outputs publicly. The installer is **NOT FOR RELEASE**.
* If something looks like a security or privacy problem (unexpected network use, files outside the places listed), stop and report it.
