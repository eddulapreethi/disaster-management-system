from collections.abc import Callable, Mapping, Sequence
from typing import Any

NotificationSender = Callable[[Mapping[str, Any]], bool]


class NotificationService:
    """Dispatch notifications through caller-provided channel adapters.

    No email, SMS, push, or in-app transport is configured by default. A sender
    must return True to confirm delivery; False or an exception is a failure.
    """

    def __init__(self, senders: Mapping[str, NotificationSender] | None = None) -> None:
        self._senders = dict(senders or {})

    def dispatch(self, notifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Send notifications and return a per-recipient delivery report."""
        results = []
        for notification in notifications:
            payload = dict(notification)
            channel = str(payload.get("channel", ""))
            sender = self._senders.get(channel)
            if sender is None:
                status = "unavailable"
                detail = f"No sender is configured for channel {channel!r}."
            else:
                try:
                    delivered = sender(payload)
                    status = "sent" if delivered is True else "failed"
                    detail = "Sender confirmed delivery." if delivered is True else "Sender did not confirm delivery."
                except Exception as error:
                    status = "failed"
                    detail = f"Sender raised {type(error).__name__}."
            results.append(
                {
                    "recipient_id": payload.get("recipient_id"),
                    "audience": payload.get("audience"),
                    "channel": channel,
                    "alert_id": payload.get("alert_id"),
                    "delivery_status": status,
                    "detail": detail,
                }
            )

        counts = {status: sum(item["delivery_status"] == status for item in results) for status in ("sent", "failed", "unavailable")}
        return {"results": results, "counts": counts, "total": len(results)}


def dispatch_alert(
    alert: Mapping[str, Any],
    *,
    citizens: Sequence[str | int] = (),
    authorities: Sequence[str | int] = (),
    response_teams: Sequence[str | int] = (),
    service: NotificationService | None = None,
) -> dict[str, Any]:
    """Build and dispatch audience notifications for a generated alert."""
    from .authority_notifications import build_authority_notifications
    from .citizen_notifications import build_citizen_notifications
    from .response_team_notifications import build_response_team_notifications

    alert_data = dict(alert)
    notifications = [
        *build_citizen_notifications(alert_data, citizens),
        *build_authority_notifications(alert_data, authorities),
        *build_response_team_notifications(alert_data, response_teams),
    ]
    dispatcher = service or NotificationService()
    return dispatcher.dispatch(notifications)
