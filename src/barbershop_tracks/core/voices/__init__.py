"""Adding the voicebanks a person has to BLT's own voices folder."""

from barbershop_tracks.core.voices.install import (
    Installed,
    VoiceInstallError,
    bank_roots,
    install_voicebank,
)

__all__ = ["Installed", "VoiceInstallError", "bank_roots", "install_voicebank"]
