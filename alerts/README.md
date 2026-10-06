# Emergency Alerts

The backend prediction endpoint uses this module to convert qualifying risk scores into persisted user alerts. Audience-specific helpers prepare notification payloads for citizens, authorities, and response teams; those audiences are not account roles.

## Risk rules

Severity follows the backend score thresholds: below 30 is low, 30–59 moderate, 60–79 high, and 80–100 critical. By default an alert is generated at score 30 or higher. Low risk remains an estimate for dashboard use.

## Delivery

Audience modules only build payloads. `NotificationService` sends only through caller-supplied channel adapters; without one, delivery is reported as `unavailable`. A sender must return `True` to be counted as sent. No SMS, email, push, or authority dispatch integration is included by default.

`EmergencyAlert.to_backend_payload()` returns the fields expected by `backend/app/schemas/alert.py`. Alerts are visible through the authenticated `GET /api/alerts` endpoint. The current integration creates an in-app record for the signed-in user; external messages are unavailable until a sender adapter and verified recipient/contact source are configured. Automated estimates are explicitly not official warnings; verify with local authorities before public or operational action.
