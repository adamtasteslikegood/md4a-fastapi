# Security policy

## Supported versions

Until the first stable release, security fixes target the latest published alpha.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's
private vulnerability reporting feature on the repository's **Security** tab.
If that feature is unavailable, contact the repository owner privately through
their GitHub profile.

Include the affected version, reproduction steps, impact, and any suggested
mitigation. Do not include live credentials or data belonging to other people.

## Deployment note

The standalone `/fetch` endpoint makes outbound HTTP requests. Configure
`MD4A_ALLOWED_HOSTS` before exposing it to untrusted clients, apply network-level
egress controls where appropriate, and do not treat application allowlisting as
the only SSRF boundary.
