"""The melisma (extender) state machines.

Two states are kept strictly apart, never reduced to one ``in_melisma`` flag:

* **typed** (``<extend type="start|continue|stop">``): explicit MusicXML state. A rest does *not*
  end it (the rest simply gets no role). It ends at ``STOP``, at a structurally conflicting lyric
  event, or at the end of the line. ``CONTINUE`` and ``STOP`` need an open typed extension.
* **inferred** (an untyped ``<extend/>``, which is what MuseScore writes): there is no explicit
  stop, so it ends at the next lyric, **at a rest** (our conservative interpretation of an
  underspecified sequence; MusicXML does not say), at humming or laughing, or at the end of the
  line. An untyped extender is never "invented" into a ``START``.

Lyric-less attacks are continuations while either state is active; otherwise they are missing.
There is no maximum length. This is independent of the syllabic word machine (``words.py``).
"""

from dataclasses import dataclass

from barbershop_tracks.core.lyrics.findings import Finding, error, warning
from barbershop_tracks.models import AttackRole, Lyric, Melisma, MelismaBasis


@dataclass(slots=True)
class Extension:
    basis: MelismaBasis
    origin: int  # attack index that opened it
    run: int = 0  # continuation attacks so far
    rest_seen: bool = False


@dataclass(frozen=True, slots=True)
class Continuation:
    """The extension state an attack belongs to, as reported to the analyzer."""

    origin: int
    position: int
    basis: MelismaBasis


class MelismaTracker:
    def __init__(self) -> None:
        self.typed: Extension | None = None
        self.inferred: Extension | None = None
        self.longest = 0
        self.interruptions: list[
            int
        ] = []  # MISSING attacks that follow an extender ended by a rest
        self._ended_by_rest = False

    # --- internal ---------------------------------------------------------------------

    def _continue(self, ext: Extension) -> Continuation:
        ext.run += 1
        self.longest = max(self.longest, ext.run)
        return Continuation(ext.origin, ext.run, ext.basis)

    def _close_typed(self, why: str, findings: list[Finding], *, warn: bool = True) -> None:
        if self.typed is not None and warn:
            findings.append(
                warning(
                    "LYRIC_MELISMA_UNCLOSED",
                    f"a typed extender started here has no 'stop' ({why})",
                    self.typed.origin,
                )
            )
        self.typed = None

    def _on_sung(self) -> None:
        self._ended_by_rest = False

    # --- attacks ----------------------------------------------------------------------

    def rest(self) -> None:
        """A rest: ends an inferred extender, leaves a typed one open."""
        if self.inferred is not None:
            self.inferred = None
            self._ended_by_rest = True
        if self.typed is not None:
            self.typed.rest_seen = True

    def unlyriced(self, index: int) -> tuple[AttackRole, Continuation | None]:
        """A sung attack with no lyric for the verse."""
        ext = self.typed or self.inferred
        if ext is not None:
            self._on_sung()
            return AttackRole.MELISMA_CONTINUATION, self._continue(ext)
        if self._ended_by_rest:
            self.interruptions.append(index)
        self._on_sung()
        return AttackRole.MISSING, None

    def syllable(self, lyric: Lyric, index: int) -> list[Finding]:
        """A text lyric: ends any extension and, if it has an extender, opens a new one."""
        findings: list[Finding] = []
        self._on_sung()
        self._close_typed("a new lyric began", findings)
        self.inferred = None
        if lyric.melisma is Melisma.UNTYPED:
            self.inferred = Extension(MelismaBasis.UNTYPED, index)
        elif lyric.melisma is Melisma.START:
            self.typed = Extension(MelismaBasis.TYPED, index)
        return findings

    def conflict(self) -> list[Finding]:
        """An attack that cannot be classified: a structural conflict ends the extension."""
        findings: list[Finding] = []
        self._on_sung()
        self._close_typed("a conflicting lyric event occurred", findings)
        self.inferred = None
        return findings

    def vocal_event(self, index: int, name: str) -> list[Finding]:
        """Humming or laughing: ends an inferred extender, conflicts with a typed one."""
        findings: list[Finding] = []
        self._on_sung()
        self.inferred = None
        if self.typed is not None:
            findings.append(
                error(
                    "LYRIC_EXTEND_SEQUENCE_INVALID",
                    f"{name} occurs while a typed extender is open; no compatible reading",
                    index,
                )
            )
            self.typed = None
        return findings

    def extension_only(
        self, lyric: Lyric, index: int
    ) -> tuple[AttackRole, Continuation | None, list[Finding]]:
        """An extender with no syllable, as an attack's own lyric."""
        self._on_sung()
        if lyric.melisma in (Melisma.CONTINUE, Melisma.STOP):
            return self._typed_event(lyric, index)
        findings = [
            error(
                "LYRIC_EXTEND_SEQUENCE_INVALID",
                "an extender with no syllable that is not 'continue' or 'stop' starts nothing",
                index,
            )
        ]
        self._close_typed("an invalid extender event occurred", findings)
        self.inferred = None
        return AttackRole.CONFLICT, None, findings

    def continuation_event(self, lyric: Lyric, index: int) -> list[Finding]:
        """An extension-only lyric on a tie continuation: feeds the state, adds no attack."""
        if lyric.melisma in (Melisma.CONTINUE, Melisma.STOP):
            # A continuation note is not an attack, so it does not lengthen the melisma run.
            return self._typed_event(lyric, index, count=False)[2]
        return [
            error(
                "LYRIC_EXTEND_SEQUENCE_INVALID",
                "an extender with no syllable that is not 'continue' or 'stop' starts nothing",
                index,
            )
        ]

    def _typed_event(
        self, lyric: Lyric, index: int, *, count: bool = True
    ) -> tuple[AttackRole, Continuation | None, list[Finding]]:
        form = "continue" if lyric.melisma is Melisma.CONTINUE else "stop"
        if self.typed is None:
            finding = error(
                "LYRIC_EXTEND_WITHOUT_START",
                f"an extender '{form}' has no open typed extender to continue",
                index,
            )
            return AttackRole.CONFLICT, None, [finding]
        continuation = (
            self._continue(self.typed)
            if count
            else Continuation(self.typed.origin, self.typed.run, self.typed.basis)
        )
        if lyric.melisma is Melisma.STOP:
            self.typed = None
        return AttackRole.MELISMA_CONTINUATION, continuation, []

    def finish(self) -> list[Finding]:
        """End of the line. An untyped extender is fine; a typed one without 'stop' is not."""
        findings: list[Finding] = []
        self._close_typed("the line ended", findings)
        self.inferred = None
        return findings
