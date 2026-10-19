# Owner release approval

Date: 2026-10-19
Approved by: Joseph Driedger, project owner

## What is approved

BLT Music Generator 0.1.0, the Windows installer `BLT-Music-Generator-0.1.0-Setup.exe`
(unsigned), SHA-256:

    18fd0a387138a5c9e2343f565e481adeee72a1ad967470ca84af7b544f1b2da0

Built on 2026-10-19 on the branch `smoother-tracks-oo-and-app-text`, model-free configuration
(`g2p_model: excluded`).

## Basis

* The owner installed this build and tested it: "it works fine" (session of 2026-10-19), and wrote
  "I approve the release".
* The owner read the list of open release-gate items (the licensing reviews, the English voicebank
  listening test and the clean-machine test) before approving.
* The installer is released unsigned, knowingly (`docs/review/evidence/code-signing-decision.md`).

## What this record does and does not cover

* It is the owner's approval of this exact build. It does not close any other gate item, and the gate
  stays closed until they are signed by the people they depend on.
* A rebuild changes the installer's checksum, and this approval then no longer applies to it.
* It was recorded by an AI assistant running `packaging/release_gate.py sign` on the owner's written
  instruction ("do it") in that session, naming the owner as the person who decided. The repository
  cannot verify the instruction independently. The owner can sign again with their own command.
