# Releasing BLT: what the owner has to do

The code and the build are ready to be released as far as a machine can make them. What remains are people's judgements,
which no tool (and no AI assistant) may supply. This page is the short route; the rules are in [release-gate.md](release-gate.md).

## 1. Get the judgements

Every row needs a real person, who writes a short signed statement (a PDF, an e-mail saved as a file, or a results file).

| Item | Who | Give them | They answer |
|---|---|---|---|
| `qt-lgpl-review` | someone qualified in open-source licensing | `review/qt-review-packet.zip` and `review/checklist-review-packet.zip` (built into `research-output/release-current/review/`) | Is BLT's use of Qt and PySide6 under the LGPL-3.0 sound (notices, written offer, replaceable libraries)? |
| `source-history-licensing` | same, or another | `review/source-history-review-packet.zip` | Is the old replacement spline in the git history acceptable, given the binary is spline-free? |
| `ai-code-authorship` | same | `review/ai-authorship-review-packet.zip` | Are the notice, the licence and the diligence about reproduced third-party text adequate for AI-assisted code? |
| `native-dependencies-review` | same | `review/native-dependencies-review-packet.zip` | Are the licence conclusions for the compiled dependencies right? |
| `g2p-model-provenance` | you, with advice | [g2p-model-provenance.md](g2p-model-provenance.md) | Confirm the release ships **without** the English pronunciation model (the only accepted answer). |
| `english-voicebank-acceptance` | a tester who is not the developer | [acceptance/english-voicebank-acceptance.md](acceptance/english-voicebank-acceptance.md) and the installer | Do the tracks, made with a real English voicebank, pass the listening checklist? |
| `clean-machine-verification` | a tester with a clean PC (and one without the Visual C++ runtime) | [acceptance/clean-machine-verification.md](acceptance/clean-machine-verification.md), the installer and the tester kit the build makes (`research-output/release-current/tester-kit`) | Do install, run, upgrade and uninstall work? |
| `code-signing-decision` | you | [release-gate.md](release-gate.md) | Sign the installer, or release it unsigned knowingly (SmartScreen warns on unsigned installers). |
| `owner-release-approval` | you | all of the above | Approve this exact build. |

The tester kit and the review packets are rebuilt by every `packaging/build.ps1` run. A reviewer's sign-off is tied to the exact files they
read: change a reviewed file and the item re-opens, so settle the text before sending packets out.

## 2. File each judgement

For each statement, put the file in the repository (for example under `compliance/evidence/`) and record it, naming **the reviewer or
tester** as `--by`, not yourself:

```
python packaging/release_gate.py sign qt-lgpl-review --by "Their Name" --role "their qualification" `
    --conclusion approved --evidence compliance/evidence/their-statement.pdf
python packaging/release_gate.py status
```

Acceptance items also take `--installer-sha256 <the installer they tested>`; `g2p-model-provenance` takes `--decision excluded`.
`compliance/` is covered by `.github/CODEOWNERS`; setting a branch-protection rule on `main` that requires your review of it is
yours to do in the repository's settings.

## 3. Publish the source with the release (LGPL)

The Qt arrangement requires the corresponding-source bundle (`BLT-Music-Generator-0.1.0-corresponding-source.zip`, made by the build
in its `compliance` folder) to be attached to the same release as the installer. The **Publish release** workflow attaches it; the gate item
`qt-source-published` is closed with the https URL of that asset once the release exists.

## 4. Run the workflow

Actions > **Publish release** > Run workflow, with the version (for example `0.1.0`). It runs the gate first and stops while
anything is open; builds the Windows package and the two macOS disk images (Apple silicon and Intel); runs the release check on the builds
it made; and then creates a **draft** GitHub release with the Windows installer, the `.dmg` files, their checksum files
(`SHA256SUMS.txt`, `SHA256SUMS-macos-<arch>.txt`), the notices and the source bundle. Nothing becomes public until you press *Publish* on the draft.

**The macOS disk images need your decision.** They are unsigned and not notarised (Gatekeeper makes people open them with right-click >
Open), and nobody has run them on a real Mac. None of the gate items above covers macOS: the acceptance and clean-machine sign-offs name the
Windows installer's checksum. Before you publish the draft, either have someone try a `.dmg` on a real Mac and keep their note, or delete the `.dmg`
files from the draft; the release notes (`RELEASE-NOTES-<version>.md`) say what the macOS builds are. Signing and notarising them needs an Apple
Developer account (not decided): `packaging/build_macos.py` has the steps, off by default and never run. The two `qt-*` review items and
`native-dependencies-review` were prepared for the Windows package; the macOS package adds its own component table
(`packaging/components-macos.json`, which the review packets do not yet include) and the Qt arrangement is restated for macOS in
`packaging/qt-statement-macos.txt`: give your reviewer both.
