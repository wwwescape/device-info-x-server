class DomainError(Exception):
    """Base class for service-layer errors. Routers never raise HTTPException
    directly for business-rule failures — they let these propagate and a
    single FastAPI exception handler maps them to the right HTTP status."""

    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class ForbiddenError(DomainError):
    status_code = 403


class UnauthorizedError(DomainError):
    status_code = 401


class ValidationError(DomainError):
    status_code = 422


class RateLimitedError(DomainError):
    status_code = 429
