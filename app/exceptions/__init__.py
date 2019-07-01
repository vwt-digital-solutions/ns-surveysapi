class AttachmentsNotFound(Exception):
    """
    Base class for registrations exceptions
    """
    def __init__(self, message, error, *args):
        self.error = error
        self.message = message
        super().__init__(message, error, *args)


class RegistrationsNotFound(Exception):
    """
    Exception returned if no registrations are found
    """
    def __init__(self, message, error, *args):
        self.error = error
        self.message = message
        super().__init__(message, error, *args)
