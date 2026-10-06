# MusicXML support

> Placeholder (M1). Populated in M3. This document will list exactly which constructs
> are supported, which produce validation WARNINGs, and which produce ERRORs.

## Repeat structures (planned)

1. Start repeats, end repeats and repeat counts.
2. First/second endings and voltas.

Any repeat structure that cannot be resolved deterministically is a validation ERROR that
prevents generation. The intended performance order is never guessed.
