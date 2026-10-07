# M4 plan: generation-readiness validation and the `check` CLI

Status: **plan, revised after review**. M4a (core readiness, no CLI) is the next implementation step;
M4b (lyric policy, rendering, CLI) follows.

M3 answered "what does the score contain and how is it performed?" M4 answers a different question:
**"can capability X safely generate from this performed score?"** M4 is not another parser
milestone. It reads the `ParseResult`, the `PerformedSong` and the lyric analysis that already exist,
adds only the checks that belong to generation, and reports. It never rewrites a score, a lyric or a
pitch.

## 1. Principles

* **Capability, not universal validity.** A score is ready *for a capability*, never "valid" in
  general. A capability is a small immutable set of requirements; validators consult those
  requirements, never a target name.
* **Source severity is not readiness disposition.** A lower-layer `ValidationIssue` is never mutated,
  re-severitied or demoted. A readiness finding *wraps* it with a disposition, an origin, a role and a
  performance location.
* **Structural errors always block; domain errors block the capabilities that consume the domain;
  warnings are classified, never defaulted.** Every structural ERROR (parsing, timeline, pitch,
  repeat/ending planning, ties, unsupported navigation) blocks every capability. An ERROR in a
  *domain* (today: lyrics, including the parser's lyric-reading errors) blocks a capability that
  consumes that domain and is INFO for one that does not (`LyricPolicy.NONE`): it cannot change what
  that capability generates. The domain is registry data, never inferred from a code's name, and the
  wrapped issue keeps severity ERROR throughout. An unknown ERROR or WARNING fails safe: it blocks.
* **No duplicated checks.** Readiness consumes what lower layers produced and adds only what they cannot
  know. A test enforces that every known issue code has a policy decision.
* **Pure and immutable.** One function in, one frozen report out. No global state, no Qt, no I/O.
* **Never guess.** Roles are explicit; pitches are never rounded or clamped; tempo is never assumed;
  chords are never "repaired"; lyrics are never filled in.
* **Load errors are not readiness errors.** A file that cannot be turned into a score is an input failure
  (`ScoreLoadError`). A loaded score with musical or parser ERRORs is a readiness report that says
  not ready.

## 2. Decisions (including the review changes)

| Topic | Decision |
|---|---|
| Structural ERRORs | Block every capability, no allow-list. Lyric-domain ERRORs block a capability that uses lyrics and are INFO for `LyricPolicy.NONE` (source severity unchanged; `LYRIC_SIMULTANEOUS_ATTACKS` is superseded by the monophony check, which still blocks where monophony is required). |
| Warnings | One registry; per-capability overrides keyed on capability *features*; unknown warning blocks. |
| Missing meter | Not blocking by itself. A missing time signature that stops measure lengths from being derived is already a parser ERROR. Any meter warning stays visible and is not promoted. |
| `MEASURE_INCOMPLETE` | Advisory, prominent; M3 semantics unchanged. |
| Roles | Explicit caller-provided mapping. Never inferred. Suggestions (the `lines` command, M4b) carry a basis and a confidence and are never applied. |
| Four roles | A **capability requirement** (`required_roles`), not a universal rule. The quartet-generation capability requires TENOR, LEAD, BARITONE and BASS; other capabilities may require fewer. |
| Lyrics | A capability **policy** (`NONE`, `AT_LEAST_ONE_COMPLETE_LINE`, `ALL_ASSIGNED_LINES_COMPLETE`) plus an optional configured `lyric_source_role`. Lead is not hard-coded as the lyric authority. |
| Reserved lyric characters | No global bad-character list. Backend-specific escaping belongs to the M6 capability; source text is preserved and the hazard warnings stay advisory. |
| Microtones | Block only capabilities that require integral MIDI pitch. Never rounded, never globally invalid. |
| Voice range | Advisory only (`VOICE_RANGE_UNUSUAL`), documented and configurable. |
| Strict mode | `--strict` means advisory findings also make this invocation not ready. |
| Exit codes | `0` ready, `1` not ready (including strict-with-warnings), `2` invocation/input/load failure. Nothing else is promised. |
| External stems | No capability is defined yet; its policy waits until that backend exists. |

## 3. M4a data model (`core/readiness`, pure)

### 3.1 Capability

```
@dataclass(frozen=True) class Capability:
    name: str
    required_roles: frozenset[VoiceRole]          # complete quartet = all four; may be empty
    all_musical_lines_accounted_for: bool         # an unassigned line with notes blocks unless ignored
    assigned_lines_must_sound: bool               # an assigned role needs sounding attacks
    monophony_required: bool
    integral_midi_pitch_required: bool
    midi_range: tuple[int, int] | None            # (0, 127) for MIDI capabilities
    tempo_required: bool
    lyric_policy: LyricPolicy                     # NONE | AT_LEAST_ONE_COMPLETE_LINE | ALL_ASSIGNED_LINES_COMPLETE
    lyric_source_role: VoiceRole | None
    typical_ranges: Mapping[VoiceRole, tuple[int, int]] | None   # advisory heuristic; None = off
    features: frozenset[Feature]                  # derived: MONOPHONY, INTEGRAL_PITCH, TEMPO, LYRICS_USED
```

Presets: `QUARTET_VOCAL` (all four roles, monophony, integral MIDI pitch within 0-127, tempo,
`AT_LEAST_ONE_COMPLETE_LINE`, no fixed lyric source, default ranges) and `TEST_TONE` (no required roles,
no lyric policy, monophony and tempo required, no pitch-integrality requirement, only assigned lines are
synthesised so unassigned lines need not be accounted for). `with_lyric_source(role)` configures the
authoritative lyric role. Validators read these fields; they never branch on `name`.

### 3.2 Assignments

`RoleAssignments(entries: tuple[tuple[VoiceRole, str], ...], ignored: tuple[str, ...])`, built from
exact source-line identifiers (`P1/s1/v1`). Raw entries are kept so the assessment can *report* problems
as findings instead of raising: unknown line (`ROLE_LINE_UNKNOWN`), duplicate role (`ROLE_DUPLICATE`),
one line given two roles (`LINE_ASSIGNED_TWICE`), a line both assigned and ignored
(`LINE_ASSIGNED_AND_IGNORED`), an unknown ignored line (`IGNORED_LINE_UNKNOWN`). No fuzzy matching.

### 3.3 Disposition, finding, report

* `Disposition`: `BLOCKING`, `ADVISORY`, `INFO`; `FindingOrigin`: `PARSE`, `PERFORMANCE`, `LYRICS`,
  `READINESS`.
* `ReadinessFinding(issue: ValidationIssue, origin, disposition, role, line_id, location:
  PerformanceLocation | None, superseded_by: str | None)`. The wrapped issue is unchanged;
  `superseded_by` records that a stronger readiness finding explains the same fact (for example
  `LYRIC_SIMULTANEOUS_ATTACKS` and `LINE_SIMULTANEOUS_NOTES`) so renderers may fold it while the
  structured report keeps both with their true severities.
* `LineSummary(line_id, role, ignored, sounding_attacks, first_start, end)`.
* `ReadinessReport(capability, findings, lines, performed_length)`: frozen; `ready` (no BLOCKING finding),
  `blocking`, `advisory`, `info`, `counts`, `clean` (no blocking and no advisory), `by_code`. Everything
  derives from `findings`; no stored flag can disagree.

### 3.4 Warning-policy registry

`core/readiness/policy.py`: `ISSUE_POLICY: Mapping[str, CodePolicy]` covering **every** issue code the
code base can emit (errors included, so each is documented). `CodePolicy(origin, severity, warning:
WarningPolicy | None)`. `WarningPolicy(default: Disposition, overrides: tuple[Override, ...], reason: str)`
where `Override(feature, active, disposition)` applies when `(feature in capability.features) == active`
(for example lyric hygiene warnings drop to INFO when `LYRICS_USED` is inactive). Rules:
ERROR -> BLOCKING always (no table needed); WARNING -> policy; WARNING without a policy -> BLOCKING.
Completeness tests: the set of codes found in `src` equals the registry's codes (a short list of known
non-code constants is excluded), every WARNING code has a `WarningPolicy`, every other code has none,
and every ERROR disposition is BLOCKING.

### 3.5 Entry point

```
assess_readiness(parsed: ParseResult, assignments: RoleAssignments,
                 capability: Capability, *, verse: str | None = None) -> ReadinessReport
```

It wraps `parsed.issues` (locations matched back from `PerformedSong.located_issues`), runs the lyric
analysis once over the performed traversal and wraps its issues and located findings, then adds the
checks below. `parsed.performed is None` is a blocking `NO_PERFORMANCE` finding.

## 4. M4a checks (the only new ones)

* **Roles**: missing required role (`ROLE_MISSING`), duplicates and unknown lines as above, an assigned
  line with no sounding attacks (`ROLE_LINE_EMPTY`, only when `assigned_lines_must_sound`), an unassigned
  line that has sounding notes (`LINE_UNASSIGNED`, only when `all_musical_lines_accounted_for`), an
  ignored line that has notes recorded as INFO (`LINE_IGNORED`). Rests never count as attacks.
* **Monophony** (assigned lines, tie-merged attacks, exact `Fraction`): simultaneous pitched attacks
  `LINE_SIMULTANEOUS_NOTES`, overlapping attacks `LINE_OVERLAPPING_NOTES`. Rests, gaps, adjacent attacks
  and tie-merged sustains are fine. One aggregated finding per line and kind (count and the first
  location). Chords are never reduced to a top or bottom note.
* **Pitch** (assigned lines): the sounding pitch is authoritative. If integral MIDI pitch is required, a
  non-integral height is `PITCH_NOT_INTEGRAL` (no rounding). If `midi_range` is set, a height outside it
  is `PITCH_OUT_OF_MIDI_RANGE`. Advisory `VOICE_RANGE_UNUSUAL` when `typical_ranges` is set and a line lies
  outside its role's generous range (a heuristic that catches clef and octave mistakes; the table is a
  module constant and a capability field, easy to change).
* **Tempo** (`tempo_required`): no performed tempo event at all is `TEMPO_MISSING`; otherwise no effective
  tempo at performed position 0 is `TEMPO_INITIAL_MISSING`. Never both, and 120 BPM is never assumed. If a
  metronome mark set no tempo, the message says so.
* **Timeline**: a non-positive performed length is `SONG_EMPTY`; an attack starting before zero or ending
  after the performed extent is `EVENT_OUTSIDE_TIMELINE`.
* **Meter and incomplete measures**: no new rules; only the registry dispositions.

## 5. Lower-layer findings and dispositions (registry content)

* Advisory for every capability: `MEASURE_INCOMPLETE`, `MEASURE_NUMBER_NONNUMERIC`, `CLEF_INVALID`,
  `DURATION_TYPE_MISMATCH`, `REPEAT_FORWARD_UNUSED`, `REPEAT_TIMES_ONE`, `REPEAT_TIMES_IGNORED`,
  `TIE_BROKEN_BY_REPEAT`, `TIE_BROKEN_BY_ENDING`, `TIE_BROKEN_BY_DISCONTINUITY`, `TIE_WITHOUT_TIED`,
  `TEMPO_ZERO_UNRESOLVED`, `METRONOME_WITHOUT_SOUND`, `CUE_NOTE_SKIPPED`.
* Lyric warnings (`LYRIC_EMPTY`, `LYRIC_LINE_EMPTY`, `LYRIC_MISSING_SUMMARY`, `LYRIC_SYLLABIC_MISSING`,
  `LYRIC_TIE_REPEATED`, `LYRIC_MELISMA_INTERRUPTED`, `LYRIC_MELISMA_UNCLOSED`, `LYRIC_ELIDED`,
  `LYRIC_TEXT_WHITESPACE`, `LYRIC_TEXT_INNER_SPACE`, `LYRIC_TEXT_TRAILING_HYPHEN`,
  `LYRIC_TEXT_RESERVED_CHARACTERS`, `LYRIC_MULTIPLE_VERSES`, `LYRIC_VERSE_MIXED_NUMBERING`): ADVISORY, dropping to INFO when the capability does not use lyrics.
  M4b adds the line-aware lyric policy (a partly covered authoritative line blocks).
* Everything else the code base emits at ERROR severity blocks.

## 6. M4b (after M4a is reviewed)

* **Lyric readiness**: apply `lyric_policy` and `lyric_source_role`: for a line selected as the
  authoritative source, partial coverage is an ERROR; non-authoritative lines are not required to have
  lyrics while propagation is an M6 concern. Missing authoritative coverage when the policy needs a line is
  an ERROR (`LYRICS_MISSING`).
* **Line suggestions** for `lines`: name-based and order-based, each with `basis` and
  `confidence`/`confirmed=False`; never applied or persisted.
* **Rendering**: `render_text` and `render_json` as pure functions in `core/readiness/render.py`.
* **CLI**: `check` and `lines`.

### 6.1 CLI

```
barbershop-tracks check SCORE [--target quartet-vocal|test-tone]
                              [--assign ROLE=LINE ...] [--ignore LINE ...] [--verse N]
                              [--format text|json] [--strict]
barbershop-tracks lines SCORE [--format text|json]
```

* `--assign TENOR=P1/s1/v1`, repeated once per assignment; `ROLE` is `tenor|lead|baritone|bass`
  (case-insensitive) and `LINE` is the exact source-line identifier as printed by `lines`. Rejected with
  exit `2`: an unknown role, an unknown line, the same role twice, one line given two roles, a line both
  assigned and ignored. No fuzzy matching.
* `--ignore P2/s1/v1`, repeated; exact identifiers only; an unknown identifier is rejected, never
  swallowed. Ignored lines that contain notes stay visible in the report as INFO.
* Friendly `--target` names resolve to capability definitions; the readiness code never sees the name.
* **Exit codes**: `0` ready; `1` not ready (a blocking finding, or an advisory finding under `--strict`);
  `2` invocation, input or load failure (bad arguments, missing file, `ScoreLoadError`). An unexpected
  internal exception is left to the normal failure path; no further code is promised.
* **JSON**: versioned from the start (`"schema": "barbershop-tracks.readiness/1"`), semantic fields rather
  than prose (`code`, `severity`, `disposition`, `role`, `line_id`, `location` with `measure_index`,
  `number`, `visit`, `repeat_pass`, `endings`, `performed_position`) plus the `message`. Exact fractions
  are strings such as `"7/2"`. Key order is fixed for snapshots but carries no meaning. Within a version
  the format only grows by adding fields.
* `lines` prints stable identifiers (copy-paste into `--assign`): part/source name, staff, voice,
  attack count, lyric presence, suggested role, basis and confidence. Output is deterministic.

## 7. Tests

* **M4a**: all four roles correct; missing role; duplicate role; unknown line; one line assigned twice;
  assigned and ignored; unassigned musical line; ignored musical line; assigned empty line;
  simultaneous, overlapping, adjacent and tie-sustained attacks; exact `Fraction` boundaries; integral
  sounding pitch; microtonal pitch blocked by one capability and allowed by another; below and above
  `midi_range`; the advisory range finding; no tempo; first tempo after zero; tempo at zero; positive
  duration; attack outside the extent; a parser ERROR always blocks; a warning whose disposition
  differs by capability; the registry completeness tests; wrapped issues unchanged (identity and equality);
  source models unchanged.
* **M4b**: lyric policy cases; rendering golden files (text and JSON); CLI through `capsys` for every
  exit code and every `--assign`/`--ignore` rejection; `lines` determinism; `.mxl` input; no network.
* The real score is never committed; a local-only smoke run exercises `check` on it.

## 8. Open items

1. The default per-role ranges for the advisory heuristic (documented in code, configurable).
2. Whether `TEST_TONE` should eventually allow microtonal pitch (the capability field already permits it).
3. The `lyric_source_role` default for `QUARTET_VOCAL` once the M6 lyric-propagation decision is made.
