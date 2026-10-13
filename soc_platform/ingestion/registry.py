"""Source-kind to parser lookup."""

from __future__ import annotations

from soc_platform.domain.enums import SourceKind
from soc_platform.domain.errors import IngestRejected
from soc_platform.ingestion.mock_edr import MockEdrParser
from soc_platform.ingestion.sigma import SigmaAlertParser
from soc_platform.ingestion.types import ParsedIngest
from soc_platform.ingestion.windows_event import WindowsEventParser


class Parser:
    source_kind: SourceKind

    def parse(self, payload: bytes) -> ParsedIngest: ...


_PARSERS: dict[SourceKind, Parser] = {
    SourceKind.SIGMA_ALERT: SigmaAlertParser(),
    SourceKind.MOCK_EDR_ALERT: MockEdrParser(),
    SourceKind.WINDOWS_EVENT: WindowsEventParser(),
}


def parser_for(source_kind: SourceKind) -> Parser:
    try:
        return _PARSERS[source_kind]
    except KeyError as exc:
        raise IngestRejected(f"unsupported source kind {source_kind}", "unsupported_source") from exc
