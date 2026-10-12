"""Only authored messages cross the UI boundary."""


class PracticeError(Exception):
    """An expected failure with a safe, actionable message."""


class StorageError(PracticeError):
    def __init__(self):
        super().__init__(
            "History could not be saved or loaded. Check local storage and retry."
        )


class ServiceError(PracticeError):
    def __init__(self):
        super().__init__(
            "The local service is unavailable or returned an unsupported response."
        )


def user_message(error):
    if isinstance(error, PracticeError):
        return str(error)
    return "This operation could not finish. Your draft is unchanged; please retry."
