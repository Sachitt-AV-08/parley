"""parley exception hierarchy."""


class ParleyError(Exception):
    """Base class for all parley errors."""


class HostNotFoundError(ParleyError):
    """No WhatsApp Desktop process / CDP endpoint could be found."""


class NotLoggedInError(ParleyError):
    """The attached host exists but is not signed into an account."""


class StoreUnavailableError(ParleyError):
    """The host is up but its internal message store could not be reached.

    parley tries several strategies (window.Store, webpack chunk scan, then the
    DOM). If all fail this is raised, and the DOM fallback is the best next
    step to inspect the rendered UI.
    """


class ProtocolError(ParleyError):
    """The host spoke CDP but not the way parley expected."""


class BudgetExceeded(ParleyError):
    """HumanPacing refused to send; see parley.pacing.BudgetExceeded."""
