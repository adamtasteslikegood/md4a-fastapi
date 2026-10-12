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

By default the client refuses destinations that are, or resolve to, loopback,
private, link-local, or other non-public addresses, including on redirects, and
connects to the address it validated. `MD4A_ALLOW_PRIVATE_ADDRESSES`,
`--allow-private-addresses`, and `allow_private_addresses=True` turn this off; do
not enable them on a service reachable by untrusted clients.

When an HTTP proxy is configured in the environment (`HTTPS_PROXY`, `HTTP_PROXY`,
`ALL_PROXY`), the proxy resolves hostnames, so md4a cannot check or pin the
address for proxied requests. It still refuses literal non-public addresses,
including spellings such as `127.1`, `2130706433`, and `0x7f000001`, and checks
hosts that bypass the proxy; the proxy must enforce the rest. `NO_PROXY` is read
the way httpx reads it: `*` anywhere disables proxying, and entries may be a
domain, an address, `localhost`, or a `scheme://host[:port]` pattern.

Direct connections are opened to the validated address, with a separate connection
pool per hostname so a connection verified for one hostname is never reused for
another at the same address. A transport passed as `transport=` is used as given
for every hostname and receives requests addressed to the validated IP; if it pools
connections, it must not be shared across hostnames you do not trust equally.
