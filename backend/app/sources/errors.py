class SourceError(Exception):
    pass


class SourceNotFoundError(SourceError):
    pass


class PermissionDeniedError(SourceError):
    pass


class InvalidSourceError(SourceError):
    pass


class InvalidFileError(SourceError):
    pass


class DuplicateVersionError(SourceError):
    pass


class InvalidTransitionError(SourceError):
    pass
