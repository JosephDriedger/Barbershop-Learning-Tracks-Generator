# The release gate

BLT's installer is marked **NOT FOR RELEASE** until every item below has a *person's* recorded sign-off. The gate is separate from
CI: a green pipeline says the code builds and the tests pass; it says nothing about licensing review, listening tests or whether
the installer works on a clean PC. **Green CI is not an input to the gate and cannot open it.**

* Data: [`compliance/release-gate.json`](../compliance/release-gate.json). Tool: `packaging/release_gate.py`. Tests: `tests/unit/test_release_gate.py`.
* Since M15. Nothing in this repository publishes, signs or uploads a release; publication stays a manual decision, and any future
  publishing automation must run `release_gate.py check --release` first and stop on a non-zero exit.

## The items

| Item | Kind | What closes it | Packet / checklist |
|---|---|---|---|
| `worldline-spline-review` | review | a qualified person, who has not read `tk::spline` and did not write or direct the replacement, reviews the replacement spline | [review/worldline-spline-review-packet.md](review/worldline-spline-review-packet.md) |
| `qt-lgpl-review` | review | a qualified person reviews BLT's LGPL-3.0 arrangement for Qt and PySide6 | [review/qt-pyside6-review-packet.md](review/qt-pyside6-review-packet.md) |
| `qt-source-published` | publication | the corresponding-source bundle is attached to the release it accompanies and the link works (evidence: its https URL) | same packet, section 8 |
| `english-voicebank-acceptance` | acceptance | a tester who is not the developer listens to tracks made with a real English voicebank and the checklist is passed | [acceptance/english-voicebank-acceptance.md](acceptance/english-voicebank-acceptance.md) |
| `clean-machine-verification` | acceptance | a tester installs, runs, upgrades and uninstalls on a clean PC, with and without the Visual C++ runtime | [acceptance/clean-machine-verification.md](acceptance/clean-machine-verification.md) |
| `code-signing-decision` | decision | the owner records whether the installer will be signed or released unsigned knowingly | this page |
| `owner-release-approval` | decision | the owner approves this exact build after reading everything above | this page |
| `upstream-plus-dictionary-answer` | review, **not required** | only if the English "plus" dictionary were ever re-included | [g2p-plus-provenance.md](g2p-plus-provenance.md) |

Besides the items, `check` fails while any component in `packaging/components.json` has status `blocker`, and in `--release` mode
it also fails unless the build being released is of the commit that is checked out, from a clean tree, with no blockers listed in its
`release-info.json` and an installer in its `SHA256SUMS.txt`.

## What a sign-off is

```
python packaging/release_gate.py sign <item> --by "<person's name>" --role "<role or qualification>" \
    --conclusion approved|approved-with-conditions [--conditions "..."] \
    --evidence <file in the repository, or https URL> [more evidence] [--installer-sha256 <sha of the installer tested>]
```

It records the date and the SHA-256 of every `subjects` file of the item (the exact files the person reviewed). The gate then insists that:

* `by` is a person: names such as Claude, an AI assistant, CI, a bot or github-actions are refused, by `sign` and by `check`;
* the conclusion is *approved* or *approved with conditions* (and the conditions are written down); *rejected*, *open* or anything else keeps the item open;
* the subjects are **unchanged**: edit a reviewed file and its item re-opens, so a review cannot be reused for different code or text;
* evidence exists: a file in the repository (a signed review letter, a tester's results file under `compliance/evidence/`) or, for a publication item, the https URL of the asset;
* for acceptance items, the installer tested is the installer being released (SHA-256 against `SHA256SUMS.txt`).

The sign-off is the owner's record of someone else's judgement: the reviewer or tester sends their written statement; the owner files it as evidence and
runs `sign` naming **the reviewer or tester** as `by`. The tool cannot check that a person really made the judgement. What protects against a faked sign-off is
process: the data file is covered by `.github/CODEOWNERS` (the owner must approve any change to `compliance/`), and the owner should set a branch-protection rule
on `main` that requires that review. (Those repository settings are the owner's to apply; they are not changed by the code.)

## How it stops publication

| Where | What happens |
|---|---|
| `packaging/build.ps1` (default) | builds as before and prints the gate's status; the artifacts stay marked NOT FOR RELEASE and `release-gate-status.txt` lists what is open |
| `packaging/build.ps1 -ForRelease` | stops at once if the gate is closed, and checks the finished build against it (`check --release`) |
| `.github/workflows/release.yml` | on a pushed version tag (`v*`) or a manual run, runs `release_gate.py check`; the workflow **fails** while anything is open. It contains no publishing step |
| `.github/workflows/ci.yml` | prints `release_gate.py status` for information; does not gate (CI must stay able to go green while reviews are pending) |

There is no override flag. To publish while an item is open, a commit would have to change `required` in `compliance/release-gate.json`: a visible change that needs the owner's approval.

## Packets and checklists are inputs, not conclusions

`python packaging/review_packets.py --out research-output/release/review` assembles the two review packets with hashes and evidence logs. They do
not say a licensing concern is resolved. They exist so that a qualified person can decide.
