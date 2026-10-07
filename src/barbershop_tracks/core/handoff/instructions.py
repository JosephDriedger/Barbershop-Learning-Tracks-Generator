"""The short, deterministic hand-off instructions written into the package."""


def instructions_text(midi_file: str) -> str:
    return (
        "BarbershopLearningTracks: OpenUtau hand-off\n"
        "============================================\n"
        "\n"
        f"This package holds {midi_file}, a four-voice MIDI file (tracks Tenor, Lead, Baritone,\n"
        "Bass, plus a Conductor track with tempo and time signature), and\n"
        "handoff-manifest.json, which records exactly what was written and what was not.\n"
        "\n"
        "Manual steps (OpenUtau is not automated in this version):\n"
        "\n"
        f"1. In OpenUtau, create a new project and import {midi_file}\n"
        "   (File > Import, MIDI). Each voice track becomes one part.\n"
        "2. Choose a voicebank for each track.\n"
        "3. Lyrics: this package does NOT contain lyrics. The notes arrive with OpenUtau's\n"
        "   default lyric until a later version of this tool prepares lyrics for OpenUtau.\n"
        '   The manifest says so under "lyrics".\n'
        "4. Render each track on its own to a WAV file (one stem per voice).\n"
        "\n"
        "Notes:\n"
        "- Timing is exact in the MIDI file. Tempo is stored as whole microseconds per quarter\n"
        "  note; the manifest lists every tempo and the (tiny) encoding error.\n"
        "- Note velocity is a constant. The score's dynamics are not exported.\n"
        "- The behaviour of OpenUtau's MIDI import is not verified by this tool. Check the part\n"
        "  lengths, tempo and pitches after importing.\n"
    )
