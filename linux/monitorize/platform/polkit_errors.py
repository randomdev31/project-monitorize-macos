"""User-facing diagnostics for unavailable Polkit authentication prompts."""


AGENT_HINT = (
    "If no password dialog appeared, install and start a Polkit authentication "
    "agent in your desktop session, then retry."
)


def authentication_error_message(detail: str) -> str | None:
    """Recognize prompt failures without treating every denial as a missing agent."""
    lowered = detail.lower()
    if any(marker in lowered for marker in (
        "no authentication agent", "no polkit authentication agent",
        "authentication agent is not available", "authentication agent not found",
        "cannot register authentication agent", "failed to register authentication agent",
        "error creating textual authentication agent",
    )):
        return (
            "Could not open the administrator authentication prompt. "
            "Install and start a Polkit authentication agent in your desktop "
            "session, then retry."
        )
    if "cancelled" in lowered or "canceled" in lowered or "dismissed" in lowered:
        return None
    if any(marker in lowered for marker in (
        "polkit denied", "not authorized", "not authorised",
        "authorization was denied", "authorization failed", "authorization was not obtained",
    )):
        return f"Administrator authorization failed. {AGENT_HINT}"
    return None
