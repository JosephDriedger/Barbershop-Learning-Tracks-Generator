# Code signing decision: release unsigned

Date: 2026-10-19
Decided by: Joseph Driedger, project owner

## The decision

The owner decided that BLT Music Generator is released **unsigned**, knowingly. In the session of
2026-10-19 the owner wrote: "don't want to deal with signing issues. just leave it unsigned".

## What was explained to the owner first

* No code-signing certificate is available to this project, and getting one needs identity verification and
  a yearly fee (or an eligible account with a signing service).
* An unsigned installer shows the publisher as unverified, and Windows SmartScreen warns on a downloaded
  unsigned installer ("Windows protected your PC"; the user chooses More info, then Run anyway).
  Some antivirus programs flag PyInstaller executables heuristically.
* The checksum published with a release (`SHA256SUMS.txt`) is the only integrity statement. Nothing in the
  installer, documents or release notes claims that the installer is trusted
  (`docs/m12-packaging.md`, "Code signing and SmartScreen").

## What this record does and does not cover

* It records only the choice between "sign" and "unsigned". It does not approve the release and does not
  close any other item of the release gate.
* It was recorded by an AI assistant running `packaging/release_gate.py sign` on the owner's written
  instruction in that session, naming the owner as the person who decided. The repository cannot verify the
  instruction independently. If the owner wants a record that is unmistakably their own, they can sign again
  with their own command.
* If the owner later decides to sign, this item should be signed again for that decision.
