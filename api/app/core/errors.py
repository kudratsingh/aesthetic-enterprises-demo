class DomainError(Exception):
    """Base for typed domain errors raised by services; translated to HTTP in main.py."""

    code = "domain_error"
    status_code = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
