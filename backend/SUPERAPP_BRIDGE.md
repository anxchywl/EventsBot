# University Superapp Identity Bridge

The Flutter coordinator app will move into the university superapp (the big
Flutter app with NFC entry cards). This backend is prepared for that migration
with a **forward-compatible identity seam** that is inert until configured:

- **Telegram bot** — unchanged (long-polling, `admin_ids`/DB role).
- **Mini app** — unchanged (Telegram `initData` HMAC).
- **Flutter standalone host** — native email/password tokens are available only
  in an explicitly enabled debug backend.

## How it works

Every Flutter endpoint funnels through `require_flutter_user`
(`app/web/flutter_auth.py`). That function now resolves identity in this order:

1. **Superapp bridge** (`app/web/superapp_bridge.py`) — if `SUPERAPP_JWT_*` is
   configured, a valid superapp-issued JWT is verified and mapped to a local
   `User` via the new `users.superapp_user_id` column (migration
   `20260706_0001`). New identities are auto-provisioned (mirrors how the mini
   app upserts Telegram users), `is_verified=True` because the superapp asserts
   identity, and role defaults to `user` — only elevated to `admin` when a
   configured role claim exactly matches the configured admin value.
2. **Native Flutter token** — accepted only when the development-only
   `FLUTTER_NATIVE_AUTH_ENABLED=true` flag is enabled under `LOG_LEVEL=DEBUG`.

The production posture is superapp-only. Native login, registration, and
previously issued native tokens are rejected unless the explicit development
flag is enabled, so shared test accounts cannot become a production backdoor.

No assumption is made about the superapp beyond "it can hand the Flutter module
a signed JWT" (standard OIDC/JWT). If instead it authenticates via a gateway-injected
header or mTLS, `superapp_bridge.py` is the *only* file to change — swap
`decode_superapp_token()`; keep `resolve_or_create_superapp_user()`.

## Turning it on (when you have superapp details)

Set these env vars (all currently unset → bridge off):

| Var | Meaning |
|-----|---------|
| `SUPERAPP_JWT_ISSUER` | expected `iss` claim (required to enable) |
| `SUPERAPP_JWT_PUBLIC_KEY` | RS256/ES256 public key, PEM (**preferred** — asymmetric) |
| `SUPERAPP_JWT_SECRET` | HS256 shared secret (only if that is all the superapp offers) |
| `SUPERAPP_JWT_AUDIENCE` | expected `aud` claim (optional but recommended) |
| `SUPERAPP_JWT_ALGORITHM` | default `RS256` |
| `SUPERAPP_USER_ID_CLAIM` | claim holding the stable subject id (default `sub`) |
| `SUPERAPP_ROLE_CLAIM` | optional claim carrying the user's role |
| `SUPERAPP_ADMIN_ROLE_VALUE` | the role-claim value that maps to coordinator/admin |

The bridge is considered enabled once `SUPERAPP_JWT_ISSUER` **and** a key
(public key or secret) are set. Prefer the asymmetric public key so this backend
never holds the superapp's signing key.

## Flutter host contract

Jas Wallet passes its access token to the feature; it does not pass a local user
ID or role. The feature calls:

```http
GET /api/flutter/auth/session
Authorization: Bearer <jas-wallet-token>
```

The response contains `user_id`, `role`, `first_name`, and `is_verified`. It
never echoes the bearer token. All later Flutter endpoints accept the same
token and resolve the same local user. On HTTP 401, the feature clears its
session-scoped cache, stops realtime updates, and invokes the host's
`onSessionExpired` callback once. The host must obtain a new Jas Wallet token
and rebuild `EventsFeature` with a new `EventsHostSession`.

The bridge copies an email claim only when the verified token also contains
`email_verified: true`. Email is profile data, never the local identity key;
the configured subject claim remains the stable account mapping.

## Remaining steps at cutover (need superapp specifics)

- **CORS / CSP**: no change is required for a native Flutter tab. If the final
  integration uses Flutter Web or a webview, add its exact origin to CORS and
  `frame-ancestors` rather than enabling a wildcard.
- **`TRUSTED_PROXY_IPS`**: set to the superapp/university gateway IP, or all
  users collapse to one rate-limit bucket.
- **Flutter build**: ship with `--dart-define=API_BASE_URL=https://<prod-host>`
  (release builds now refuse to run without it).
- **Development access**: use `LOG_LEVEL=DEBUG` and
  `FLUTTER_NATIVE_AUTH_ENABLED=true` only in an isolated development
  environment. Leave the flag unset/false in production.
- **Role provisioning**: decide how superapp roles/groups map to coordinator
  (`admin`) vs club-head (`user`) and set `SUPERAPP_ROLE_CLAIM` /
  `SUPERAPP_ADMIN_ROLE_VALUE` accordingly.
