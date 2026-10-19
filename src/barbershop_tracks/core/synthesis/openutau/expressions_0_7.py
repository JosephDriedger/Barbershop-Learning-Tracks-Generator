"""The fixed default-expression block that OpenUtau 0.1.565 writes (USTX 0.7).

Copied verbatim from a project saved by that release (expressions and the selector keys), kept as
text so that serialization is exact and deterministic. It is the release's own default set; the
writer does not edit it. A different OpenUtau release needs a different adapter, not an edit here.

The one deliberate departure is the smoothing below: the attack default is lowered so that syllables
start more softly. ``SMOOTH_NOTES = False`` writes the release's
block unchanged.
"""

# Smoothing of note starts (unverified by ear: compare a render against the release defaults
# before keeping it). OpenUtau 0.1.565 (UPhoneme.ValidateEnvelope): the attack ("atk") is the
# volume at the end of a note's fade-in, as a percent of full volume, so 100 starts every note
# at full level and a lower value gives a softer onset.
# The velocity ("vel") is left at the release default on purpose: a value under 100 lengthens
# the overlap with the previous note, but it also moves where notes start and end. With 90 the
# Tenor stem of "San Francisco Bay Blues" (Bennett ENG) ended 4.5 ms past the score and the mix
# refused it (MIX_STEM_TOO_LONG); with 100 the same score renders.
SMOOTH_NOTES = True
SMOOTH_ATTACK = 80  # release default 100
SMOOTH_VELOCITY = 100  # the release default: lowering it moves note ends (see above)

_RELEASE_BLOCK = """\
expressions:
  dyn:
    name: dynamics (curve)
    abbr: dyn
    type: Curve
    min: -240
    max: 120
    default_value: 0
    is_flag: false
    flag: ""
  pitd:
    name: pitch deviation (curve)
    abbr: pitd
    type: Curve
    min: -1200
    max: 1200
    default_value: 0
    is_flag: false
    flag: ""
  clr:
    name: voice color
    abbr: clr
    type: Options
    min: 0
    max: -1
    default_value: 0
    is_flag: false
    options: []
  eng:
    name: resampler engine
    abbr: eng
    type: Options
    min: 0
    max: 1
    default_value: 0
    is_flag: false
    options:
    - ""
    - worldline
  vel:
    name: velocity
    abbr: vel
    type: Numerical
    min: 0
    max: 200
    default_value: 100
    is_flag: false
    flag: ""
  vol:
    name: volume
    abbr: vol
    type: Numerical
    min: 0
    max: 200
    default_value: 100
    is_flag: false
    flag: ""
  atk:
    name: attack
    abbr: atk
    type: Numerical
    min: 0
    max: 200
    default_value: 100
    is_flag: false
    flag: ""
  dec:
    name: decay
    abbr: dec
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
  gen:
    name: gender
    abbr: gen
    type: Numerical
    min: -100
    max: 100
    default_value: 0
    is_flag: true
    flag: g
  genc:
    name: gender (curve)
    abbr: genc
    type: Curve
    min: -100
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
  bre:
    name: breath
    abbr: bre
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: true
    flag: B
  brec:
    name: breathiness (curve)
    abbr: brec
    type: Curve
    min: -100
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
  lpf:
    name: lowpass
    abbr: lpf
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: true
    flag: H
  norm:
    name: normalize
    abbr: norm
    type: Numerical
    min: 0
    max: 100
    default_value: 86
    is_flag: true
    flag: P
  mod:
    name: modulation
    abbr: mod
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
  mod+:
    name: modulation plus
    abbr: mod+
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
  alt:
    name: alternate
    abbr: alt
    type: Numerical
    min: 0
    max: 16
    default_value: 0
    is_flag: false
    flag: ""
  dir:
    name: direct
    abbr: dir
    type: Options
    min: 0
    max: 1
    default_value: 0
    is_flag: false
    options:
    - off
    - on
  shft:
    name: tone shift
    abbr: shft
    type: Numerical
    min: -36
    max: 36
    default_value: 0
    is_flag: false
    flag: ""
  shfc:
    name: tone shift (curve)
    abbr: shfc
    type: Curve
    min: -1200
    max: 1200
    default_value: 0
    is_flag: false
    flag: ""
  tenc:
    name: tension (curve)
    abbr: tenc
    type: Curve
    min: -100
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
  voic:
    name: voicing (curve)
    abbr: voic
    type: Curve
    min: 0
    max: 100
    default_value: 100
    is_flag: false
    flag: ""
exp_selectors:
- dyn
- pitd
- clr
- eng
- vel
- vol
- atk
- dec
- gen
- bre
exp_primary: 0
exp_secondary: 1
key: 0
"""


def _with_default(block: str, abbr: str, was: int, now: int) -> str:
    """``block`` with the default of expression ``abbr`` changed from ``was`` to ``now``."""
    start = block.index(f"    abbr: {abbr}\n")
    marker = "    default_value: "
    begin = block.index(marker, start) + len(marker)
    end = block.index("\n", begin)
    if block[begin:end] != str(was):
        raise ValueError(f"the {abbr} default is {block[begin:end]}, not the release's {was}")
    return block[:begin] + str(now) + block[end:]


STATIC_BLOCK = (
    _with_default(
        _with_default(_RELEASE_BLOCK, "atk", 100, SMOOTH_ATTACK), "vel", 100, SMOOTH_VELOCITY
    )
    if SMOOTH_NOTES
    else _RELEASE_BLOCK
)
