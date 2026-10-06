"""Safe XML parsing for MusicXML.

MuseScore and other MusicXML writers emit a ``DOCTYPE`` with a PUBLIC identifier, so DTDs
are *allowed*. Everything dangerous stays forbidden: entity declarations (so no expansion),
and external resources. The parser never fetches a DTD or touches the network, and nothing
is stripped or rewritten to make a file parse.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import defusedxml.ElementTree as DefusedET
from defusedxml.common import DefusedXmlException, EntitiesForbidden, ExternalReferenceForbidden

from barbershop_tracks.core.errors import ScoreXmlError, ScoreXmlSecurityError

_MAX_DETAIL = 120


def parse_xml(data: bytes, *, what: str, path: Path | None = None) -> ET.Element:
    """Parse ``data`` and return the root element.

    Raises ``ScoreXmlSecurityError`` for forbidden constructs and ``ScoreXmlError`` for empty
    or malformed XML. Messages never include document content beyond a short parser
    diagnostic and the position of the problem.
    """
    if not data.strip():
        raise ScoreXmlError(f"{what} is empty", path=path)
    try:
        root: ET.Element = DefusedET.fromstring(
            data, forbid_dtd=False, forbid_entities=True, forbid_external=True
        )
    except EntitiesForbidden as exc:
        raise ScoreXmlSecurityError(
            f"{what} declares an XML entity, which is not allowed", path=path
        ) from exc
    except ExternalReferenceForbidden as exc:
        raise ScoreXmlSecurityError(
            f"{what} refers to an external resource, which is not allowed", path=path
        ) from exc
    except DefusedXmlException as exc:
        raise ScoreXmlSecurityError(
            f"{what} uses an XML construct that is not allowed", path=path
        ) from exc
    except (ET.ParseError, ValueError) as exc:
        raise ScoreXmlError(f"{what} is not well-formed XML ({_short(exc)})", path=path) from exc
    return root


def _short(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= _MAX_DETAIL else text[: _MAX_DETAIL - 3] + "..."
