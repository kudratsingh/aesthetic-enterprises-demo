class DomainError(Exception):
    """Base for typed domain errors raised by services; translated to HTTP in main.py."""

    code = "domain_error"
    status_code = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class InvalidCredentialsError(DomainError):
    code = "invalid_credentials"
    status_code = 401


class RoleForbiddenError(DomainError):
    """Actor's role is not allowed to perform this operation (permissions matrix)."""

    code = "role_forbidden"
    status_code = 403


class NotFoundError(DomainError):
    """Resource missing — or invisible to this tenant, which must look identical."""

    code = "not_found"
    status_code = 404


class ReportLockedError(DomainError):
    """Invariant 2: locked revenue reports are immutable; use create_correction."""

    code = "report_locked"
    status_code = 409


class ReportStateError(DomainError):
    """Operation not valid for the report's current lifecycle state."""

    code = "report_state"
    status_code = 409


class InvoiceStateError(DomainError):
    """Operation not valid for the invoice/run state (e.g. superseded run)."""

    code = "invoice_state"
    status_code = 409
