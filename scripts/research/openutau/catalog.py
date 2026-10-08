"""The experiment catalog: stable IDs, inputs, manual steps, what to observe, how to classify.

Someone else with OpenUtau should be able to repeat each experiment from this description alone.
Part A artifacts are named by recipe (``recipes_part_a``); Part B experiments are their own inputs
(``recipes_part_b``); Part C experiments have no generated input.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: str
    part: str
    title: str
    input_id: str | None  # an Part A recipe id, a Part B experiment id, or None (Part C)
    steps: tuple[str, ...]
    observe: tuple[str, ...]
    criteria: str
    requires_voicebank: bool = False
    requires_manual_openutau: bool = True


_A_IMPORT = (
    "Run `python scripts/research/openutau/generate.py`.",
    "In OpenUtau (record the exact version/build), create a new project and import the generated "
    "<recipe>.mid from research-output/openutau/A/<recipe>/<recipe>.handoff/ (record the import "
    "method and any import setting or dialog).",
)
_A_CRITERIA = (
    "MATCH if every observed value equals the expected table; BENIGN_DIFFERENCE if only the "
    "representation differs; INTEROPERABILITY_PROBLEM if any musical value is wrong or lost; "
    "UNKNOWN if it could not be established numerically."
)


def _a(
    experiment_id: str,
    title: str,
    recipe: str,
    observe: tuple[str, ...],
    *,
    extra: tuple[str, ...] = (),
    voicebank: bool = False,
    criteria: str = _A_CRITERIA,
) -> Experiment:
    return Experiment(
        experiment_id, "A", title, recipe, _A_IMPORT + extra, observe, criteria, voicebank
    )


def _b(
    experiment_id: str, title: str, observe: tuple[str, ...], *, voicebank: bool = False
) -> Experiment:
    return Experiment(
        experiment_id,
        "B",
        title,
        experiment_id,
        (
            "Run `python scripts/research/openutau/generate.py`.",
            "In OpenUtau, import research-output/openutau/B/<experiment>.mid (record the import "
            "method).",
            "For each note record the lyric OpenUtau shows (from the project/note properties, not "
            "from how it sounds).",
        ),
        observe,
        "MATCH if each imported lyric equals the lyric event sent and continuation tokens behave "
        "as the contract needs; otherwise classify what differs (BENIGN_DIFFERENCE, "
        "INTEROPERABILITY_PROBLEM) with the exact strings in details.",
        voicebank,
    )


_LYRIC_FIELDS = (
    "per note: lyric text sent",
    "per note: lyric text imported",
    "notes without lyric",
)

CATALOG: tuple[Experiment, ...] = (
    _a(
        "A01_FILE_ACCEPTANCE",
        "Does the M5 MIDI import; which tracks appear",
        "baseline",
        ("import success or failure", "errors or dialogs", "tracks listed after import"),
    ),
    _a(
        "A02_VOICE_TRACKS",
        "Tenor/Lead/Baritone/Bass tracks",
        "baseline",
        (
            "per track: imported name, order, distinct track, note count",
            "whether the MIDI channel affected the import",
        ),
    ),
    _a(
        "A03_CONDUCTOR",
        "What happens to the meta-only conductor track",
        "baseline",
        ("conductor ignored, imported as an empty track, used only for global metadata, or other",),
    ),
    _a(
        "A04_PITCH",
        "Expected MIDI note numbers vs imported pitches (sounding pitch)",
        "pitches",
        ("per note: MIDI note expected vs imported pitch",),
        criteria=_A_CRITERIA,
    ),
    _a(
        "A05_TIMING_BASIC",
        "Exact-grid note start/duration/end",
        "baseline",
        ("per note: start, duration, end (project/numeric values)",),
    ),
    _a(
        "A06_TIMING_GRID",
        "Internal resolution, scaling and rounding of imported ticks",
        "grid",
        (
            "OpenUtau's internal resolution",
            "per note: start and duration in OpenUtau units",
            "whether ticks are copied, scaled or transformed; is scaling exact; any rounding",
        ),
        extra=("Inspect the saved project (or another numeric view); do not infer from snapping.",),
    ),
    _a(
        "A06_TIMING_GRID_PPQ960",
        "PPQ discriminator: ticks copied, rescaled exactly, or rounded",
        "grid_ppq960",
        (
            "OpenUtau's project resolution (USTX `resolution`)",
            "per note: MIDI tick and PPQ (expected table), the OpenUtau position and duration",
            "musical position tick/PPQ versus OpenUtau position/resolution, for starts and "
            "durations: exact copy, exact rescale, rounded rescale or other",
            "the 1/64-quarter probe (tick 15 at PPQ 960): rounded, truncated or kept",
        ),
        extra=("Save a temporary project and run observe.py ustx-summary on it.",),
    ),
    _a(
        "A07_TEMPO",
        "Tempo map: source BPM, MIDI value, OpenUtau value",
        "tempo",
        (
            "per tempo event: position; exact score BPM (expected table), MIDI-encoded "
            "microseconds per quarter (expected table), and the OpenUtau value. Compare OpenUtau "
            "to the MIDI-encoded value, not to the pre-encoding exact BPM",
        ),
    ),
    _a(
        "A08_METER",
        "Explicit meter events vs imported meter state",
        "meter",
        ("per meter event: position, numerator, denominator as imported",),
    ),
    _a(
        "A09_PICKUP",
        "Pickup timing and what happens to the pickup concept",
        "pickup",
        ("note timing", "whether any notion of a pickup measure survives (not timing corruption)"),
    ),
    _a(
        "A10_PERFORMED_REPEATS",
        "Performed (repeat-expanded) sequence",
        "repeats",
        (
            "note count",
            "positions of the repeated material",
            "the tempo and meter events replayed at the repeat: retained, deduplicated, "
            "represented differently or unexpected (an equivalent declaration that is "
            "deduplicated without changing effective playback is a BENIGN_DIFFERENCE)",
        ),
    ),
    _a(
        "A16_STEM_ALIGNMENT",
        "Do exported stems share the global timeline origin (entrance offsets preserved)?",
        "stem_alignment",
        (
            "per stem: sample rate, total frames and duration",
            "expected entrance (beat 0, 1, 2, 3 at 120 BPM = 0, 0.5, 1.0, 1.5 s) versus the "
            "measured first non-silent region, examining the waveform envelope rather than the "
            "first nonzero sample (synthesis attack latency, silence threshold)",
            "expected final note end (3, 4, 5, 6 beats = 1.5, 2.0, 2.5, 3.0 s) versus the measured "
            "last non-silent region (release tail)",
            "does the Bass stem contain its leading silence, or does it start at its first note",
        ),
        extra=(
            "File > Open the .mid; assign the singer to all four tracks; leave every track unmuted "
            "and nothing soloed.",
            "Export with File > Export Audio > Export Wav Files To..., then measure the WAVs.",
        ),
        voicebank=True,
        criteria=(
            "MATCH if every stem preserves the global origin (leading silence equal to its "
            "entrance, "
            "within synthesis latency); INTEROPERABILITY_PROBLEM if stems start at their own first "
            "note; UNKNOWN if latency prevents a definitive conclusion."
        ),
    ),
    _a(
        "A11_ADJACENT_NOTES",
        "note-off and note-on at the same tick",
        "adjacent",
        ("per note: start/end; overlap, truncation, dropped attack, or merge",),
    ),
    _a(
        "A12_VELOCITY",
        "What happens to constant note-on velocity 80",
        "baseline",
        ("preserved, mapped to another parameter, or ignored",),
    ),
    _a(
        "A13_SINGER",
        "Singer after plain import",
        "baseline",
        ("singer assigned automatically or none", "whether it depends on application defaults"),
        voicebank=True,
    ),
    _a(
        "A14_PHONEMIZER",
        "Phonemizer after plain import",
        "baseline",
        ("assigned? which?", "from singer, default or application state"),
        voicebank=True,
    ),
    _a(
        "A15_RENDER_WORKFLOW",
        "Manual workflow for one WAV per voice",
        "baseline",
        (
            "menu/action used",
            "all four tracks in one operation?",
            "output file naming",
            "mute/solo effect",
            "does rendering require a singer or phonemizer",
            "sample rate, start alignment and length",
        ),
        voicebank=True,
    ),
    _b(
        "B01_SYLLABLES",
        "One syllable per note, multisyllable, repeated word, punctuation",
        _LYRIC_FIELDS,
    ),
    _b(
        "B02_MISSING_LYRIC", "A note with no lyric event between lyric-bearing notes", _LYRIC_FIELDS
    ),
    _b("B03_PLUS", "Literal + as the continuation", _LYRIC_FIELDS),
    _b("B04_PLUS_TILDE", "Literal +~ as the continuation", _LYRIC_FIELDS),
    _b("B05_MELISMA_PLUS", "Melisma, first syllable then +, +", _LYRIC_FIELDS),
    _b("B05_MELISMA_PLUS_TILDE", "Melisma, first syllable then +~, +~", _LYRIC_FIELDS),
    _b("B05_MELISMA_MIXED", "Melisma, first syllable then +, +~", _LYRIC_FIELDS),
    _b("B05_MELISMA_HYPHEN", "Melisma, first syllable then -, -", _LYRIC_FIELDS),
    _b(
        "B06_PITCH_CONTINUATION",
        "Continuation across same, changed and repeated adjacent pitch",
        (*_LYRIC_FIELDS, "whether behaviour depends on pitch movement as well as tokens"),
    ),
    _b(
        "B07_FOUR_TRACKS",
        "Lyric events on all four tracks",
        (*_LYRIC_FIELDS, "per track: its own words?"),
    ),
    _b(
        "B08_ONE_SOURCE_TRACK",
        "Lyrics on one track only",
        (*_LYRIC_FIELDS, "what the other three tracks received (no propagation assumed)"),
    ),
    _b("B09_TEXT", "Apostrophe, hyphen, comma, period, ? and !", _LYRIC_FIELDS),
    Experiment(
        "C01_USTX_STRUCTURE",
        "C",
        "USTX structure of a tiny OpenUtau-created project",
        None,
        ("Create a tiny project in OpenUtau, save it, and run `observe.py ustx-summary FILE`.",),
        (
            "OpenUtau version",
            "USTX version/schema indicator",
            "track, note timing, tempo, meter, lyric representations",
            "singer and phonemizer identity",
            "expressions/settings relevant to basic synthesis",
        ),
        "A description; classification is UNKNOWN unless a contract statement is established.",
        False,
    ),
    Experiment(
        "C02_STABILITY",
        "C",
        "What the file contains vs what OpenUtau promises is stable",
        None,
        ("Read OpenUtau's documentation/release notes for compatibility and versioning.",),
        ("documented compatibility/versioning evidence, if any",),
        "A readable YAML file is not a stability promise.",
        False,
        False,
    ),
    Experiment(
        "C03_ROUND_TRIP",
        "C",
        "Create, save, inspect, reopen a tiny project",
        None,
        ("Create and save a tiny project, inspect it, reopen it in OpenUtau.",),
        ("reopens unchanged?", "anything normalised or lost"),
        "Script-generated or modified projects are a separate later experiment.",
        False,
    ),
    Experiment(
        "C04_MINIMALITY",
        "C",
        "What a useful project can omit",
        None,
        (
            "Test whether a project opens usefully without singer, phonemizer, expressions, "
            "renderer settings, voicebank metadata.",
        ),
        ("per omitted element: accepted?, effect",),
        "Decides whether generic USTX generation would improve on MIDI.",
        True,
    ),
    Experiment(
        "C05_SINGER_PORTABILITY",
        "C",
        "How singer identity is stored",
        None,
        ("Inspect a saved project's singer field(s).",),
        ("stable id, path, display name or installation-specific identifier",),
        "Machine-dependent identity materially affects whether BLT should generate projects.",
        True,
    ),
    Experiment(
        "C06_PHONEMIZER_PORTABILITY",
        "C",
        "How phonemizer identity is stored",
        None,
        ("Inspect a saved project's phonemizer field(s).",),
        ("name/identifier form; portable between installations?",),
        "A phonemizer name is not assumed portable.",
        True,
    ),
    Experiment(
        "C07_AUTOMATION",
        "C",
        "A documented stable mechanism without GUI interaction",
        None,
        (
            "Read documentation, source and release behaviour for open/import, singer "
            "selection, render and stem export without the GUI.",
        ),
        ("per capability: DOCUMENTED_STABLE, DOCUMENTED_EXPERIMENTAL, UNDOCUMENTED or NOT_FOUND",),
        "Undocumented flags and internal APIs are not promoted into the architecture. "
        "NOT_FOUND means the documented/current sources listed in the report were searched and "
        "no stable interface was found, not that none exists. Record links and provenance.",
        False,
        False,
    ),
)

BY_ID: dict[str, Experiment] = {e.experiment_id: e for e in CATALOG}
