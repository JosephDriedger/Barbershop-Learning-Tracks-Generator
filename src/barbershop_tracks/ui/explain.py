"""Turn a pipeline failure into words a singer can act on. No Qt here.

Every :class:`Explanation` has a plain title, a short explanation, concrete corrective steps and,
kept separate, the technical detail (error code, underlying message, findings). The primary text
never names the singing engine's internals.
"""

from dataclasses import dataclass

from barbershop_tracks.core.pipeline import ErrorCategory, PipelineError


@dataclass(frozen=True, slots=True)
class Explanation:
    kind: str  # a stable key the tests and the window use
    title: str
    summary: str
    steps: tuple[str, ...] = ()
    technical: str = ""
    cancelled: bool = False
    review: bool = False


def _technical(error: PipelineError) -> str:
    lines = [f"{error.code} ({error.category.value}): {error.message}"]
    for finding in error.details.get("findings", []):
        where = " ".join(
            str(part)
            for part in (finding.get("voice"), finding.get("line"), finding.get("where"))
            if part
        )
        lines.append(
            f"  {finding['code']}: {finding['message']}" + (f" [{where}]" if where else "")
        )
    for key in ("stderr", "exit_code", "installed"):
        if error.details.get(key) not in (None, "", []):
            lines.append(f"  {key}: {error.details[key]}")
    return "\n".join(lines)


def _pronunciation(error: PipelineError) -> Explanation:
    """The words the dictionary lacks, with voice and bar; BLT never guesses or drops one."""
    places: dict[tuple[str, str], list[str]] = {}
    for item in error.details.get("unknown_words", []):
        key = (str(item.get("word", "")), str(item.get("where", "")))
        places.setdefault(key, []).append(str(item.get("voice", "")))
    pieces = {
        (str(i.get("word", "")), str(i.get("where", "")))
        for i in error.details.get("unknown_words", [])
        if i.get("fragment")
    }
    lines = [
        f'"{word}": {where} ({", ".join(voices)})'
        + (" [a syllable of a longer word]" if (word, where) in pieces else "")
        for (word, where), voices in places.items()
    ]
    words = sorted({word for word, _ in places})
    shown = "\n".join(f"  {line}" for line in lines[:12])
    if len(lines) > 12:
        shown += f"\n  ... and {len(lines) - 12} more places"
    which = f'"{words[0]}"' if len(words) == 1 else f"{len(words)} words"
    return Explanation(
        "pronunciation_unknown",
        "BLT does not know how to pronounce some words",
        f"The pronunciation dictionary has no entry for {which}, and BLT will not guess or leave "
        "a syllable out, so nothing was generated.\n" + (shown or "See the technical details."),
        (
            "Change each word in your score to a spelling the dictionary knows, written the way "
            "it is sung (for example 'every' for ev'ry, 'over' for o'er), save the score and "
            "choose it again.",
            *(
                (
                    "A word marked 'a syllable of a longer word' is only part of a word this voice "
                    "does not sing whole (for example it holds one note under several syllables of "
                    "the Lead's word), so it cannot be looked up as the word. Give that voice its "
                    "own lyric on that note, written as a word the dictionary knows.",
                )
                if any(i.get("fragment") for i in error.details.get("unknown_words", []))
                else ()
            ),
            "BLT never changes your score's own words.",
        ),
        _technical(error) + "\n" + "\n".join(f"  {line}" for line in lines),
    )


def _source(error: PipelineError) -> Explanation:
    codes = {f["code"] for f in error.details.get("findings", [])}
    text = _technical(error)
    if any("TEMPO" in c for c in codes):
        return Explanation(
            "missing_tempo",
            "The score has no tempo",
            "The score does not say how fast it should be played, and BLT will not guess.",
            (
                "Open the score in your notation program and add a tempo marking at the start.",
                "Export it as MusicXML again and load the new file.",
            ),
            text,
        )
    if any("TIME_SIGNATURE" in c or "METER" in c for c in codes):
        return Explanation(
            "missing_meter",
            "The score has no time signature",
            "The score does not give a time signature (or uses one BLT cannot reproduce exactly).",
            (
                "Add a time signature at the start of the score and export MusicXML again.",
                "Pickup bars followed by a change of time signature are not supported yet.",
            ),
            text,
        )
    if any("ROLE" in c or "ASSIGN" in c or "UNACCOUNTED" in c for c in codes):
        return Explanation(
            "incomplete_mapping",
            "The voice parts are not fully assigned",
            "Every musical line has to be given to Tenor, Lead, Baritone or Bass, or ignored.",
            ("Check the Voice Assignment section and decide for each line.",),
            text,
        )
    if error.code in ("SCORE_LOAD_FAILED", "SCORE_UNREADABLE", "NO_PERFORMANCE"):
        return Explanation(
            "invalid_score",
            "This file could not be read as a score",
            error.message,
            (
                "Make sure the file is MusicXML (.musicxml, .xml or .mxl).",
                "In MuseScore use File > Export > MusicXML.",
            ),
            text,
        )
    return Explanation(
        "invalid_score",
        "The score cannot be used as it is",
        error.message,
        ("Open 'Technical details' to see exactly what the score is missing.",),
        text,
    )


def _configuration(error: PipelineError) -> Explanation:
    code, text = error.code, _technical(error)
    if code == "SINGER_NOT_CHOSEN":
        return Explanation(
            "missing_singer",
            "Choose a singing voice",
            "Each of the four parts needs a singing voice.",
            ("Pick a voice for every part in the Singing Voices section.",),
            text,
        )
    lowered = error.message.lower()
    if code in ("SINGER_NOT_FOUND", "SINGERS_DIR_MISSING") or (
        code == "HOST_UNRESOLVED" and "singer" in lowered
    ):
        return Explanation(
            "missing_singer",
            "A singing voice was not found",
            "The voice you chose is not installed in the voices folder, or the folder is not set.",
            (
                "Check the voices folder and press Refresh.",
                "Choose an installed voice for each part again.",
            ),
            text,
        )
    if code == "PHONEMIZER_REMOVED":
        return Explanation(
            "engine_setting",
            "That pronunciation engine is not in this version of BLT",
            "Arpasing+ and English C+V need an English dictionary whose origin could not be "
            "verified, so BLT does not include them.",
            (
                "Open Advanced settings and clear the pronunciation engine to use the default, or",
                "type OpenUtau.Plugin.Builtin.ArpasingPhonemizer for a voicebank built for "
                "ARPAsing.",
            ),
            text,
        )
    if code in ("HOST_UNRESOLVED", "USTX_PHONEMIZER_REF", "USTX_RENDERER_UNKNOWN"):
        return Explanation(
            "engine_setting",
            "A singing setting is not valid",
            "The pronunciation or voice-quality setting you chose is not available.",
            ("Open Advanced settings and return the engine choices to their defaults.",),
            text,
        )
    if code == "FFMPEG_NOT_CONFIGURED" or code.startswith("MIX_FFMPEG"):
        return Explanation(
            "ffmpeg",
            "MP3 needs FFmpeg",
            "BLT makes MP3 files with FFmpeg, which is not installed with BLT.",
            (
                "Choose the location of ffmpeg.exe in the output settings, or",
                "choose WAV only, which needs nothing extra.",
            ),
            text,
        )
    if code == "OUTPUT_EXISTS":
        return Explanation(
            "output_exists",
            "That package already exists",
            "A set of tracks with this name is already in the output folder.",
            ("Tick 'Replace existing tracks', or change the package name.",),
            text,
        )
    if code == "OUTPUT_FOREIGN":
        return Explanation(
            "output_foreign",
            "A folder with that name already exists",
            "A folder with the package's name exists but was not made by BLT, so it is left alone.",
            ("Choose another package name or output folder.",),
            text,
        )
    if code == "VC_RUNTIME_MISSING":
        return Explanation(
            "vc_runtime",
            "A Microsoft component is missing",
            "BLT needs Microsoft's Visual C++ Redistributable, which is free but not part of BLT.",
            (
                "Download “Microsoft Visual C++ Redistributable (x64)” from Microsoft "
                "(learn.microsoft.com, “latest supported Visual C++ Redistributable”) and run it.",
                "Without internet: download it elsewhere, copy vc_redist.x64.exe over and run it.",
                "Then start BLT again.",
            ),
            text,
        )
    if code in ("HOST_NOT_FOUND", "HOST_INSTALL_FAILED") or code.startswith("HOST_BINARIES"):
        return Explanation(
            "component_missing",
            "A BLT component is missing",
            "The part of BLT that sings the voices could not be found or started.",
            (
                "Open Advanced settings and check the location of the singing engine.",
                "Reinstalling BLT normally fixes this.",
            ),
            text,
        )
    return Explanation(
        "configuration",
        "BLT is not set up correctly for this",
        error.message,
        ("See the technical details for the exact setting.",),
        text,
    )


def _audio(error: PipelineError) -> Explanation:
    code, text = error.code, _technical(error)
    if code.startswith("MIX_MP3") or code.startswith("MIX_FFMPEG"):
        return Explanation(
            "ffmpeg_failed",
            "The MP3 files could not be made",
            "FFmpeg did not produce valid MP3 files. Nothing was saved.",
            ("Check that the FFmpeg you chose works, or choose WAV only.",),
            text,
        )
    if code.startswith("STEM_"):
        steps = [
            "Open 'Technical details' to see which part and notes.",
            "Fix those lyrics in the lyric review, or choose another singing voice.",
        ]
        if "pronunciation dictionary" in error.message:
            steps.insert(
                1,
                "If a word is missing from the pronunciation dictionary, write it the way it "
                "sounds with ordinary words (for example 'every' for ev'ry) in the lyric review.",
            )
        return Explanation(
            "audio_validation",
            "A voice came out silent or wrong",
            "The recording of one part did not pass checks, so nothing was saved. This usually "
            "means the chosen voice cannot sing one of the syllables.",
            tuple(steps),
            text,
        )
    return Explanation(
        "audio_failed",
        "The tracks could not be completed",
        "The recordings or the mix did not pass checks, so nothing was saved.",
        ("Try again; if it repeats, see the technical details.",),
        text,
    )


def explain(error: PipelineError) -> Explanation:
    category = error.category
    if error.code == "PRONUNCIATION_UNKNOWN":
        return _pronunciation(error)
    text = _technical(error)
    if category is ErrorCategory.CANCELLED:
        return Explanation(
            "cancelled",
            "Generation was cancelled",
            "Nothing was saved, and any earlier tracks are untouched.",
            (),
            text,
            cancelled=True,
        )
    if category is ErrorCategory.REVIEW:
        return Explanation(
            "lyrics",
            "Some notes still need lyrics",
            "BLT never invents lyrics or copies them between parts. Decide what each of these "
            "notes is sung to.",
            ("Open the lyric review, fill in and approve each note.",),
            text,
            review=True,
        )
    if category is ErrorCategory.SOURCE:
        return _source(error)
    if category is ErrorCategory.CONFIGURATION:
        return _configuration(error)
    if category is ErrorCategory.SYNTHESIS:
        return Explanation(
            "synthesis",
            "The voices could not be sung",
            "The singing engine stopped with an error. Nothing was saved.",
            ("Try again.", "If it repeats, open the technical details and report them."),
            text,
        )
    if category is ErrorCategory.TIMEOUT:
        return Explanation(
            "timeout",
            "It took too long",
            "Generation was stopped because it exceeded the time limit.",
            ("Raise the time limit in Advanced settings and try again.",),
            text,
        )
    return _audio(error)
