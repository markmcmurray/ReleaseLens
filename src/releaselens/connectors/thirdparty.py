"""ThirdPartyConnector — stub for v2 work (architecture.md §17, ADR-0006)."""


class ThirdPartyConnector:
    name = "thirdparty"

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(
            "ThirdPartyConnector is a v2 stub. See architecture.md §17 / ADR-0006."
        )
