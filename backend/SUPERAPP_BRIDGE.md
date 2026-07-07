# University Superapp Identity Bridge

The Flutter coordinator app will move into the university superapp (the big
Flutter app with NFC entry cards). This backend is prepared for that migration
with a **forward-compatible identity seam** that is **inert until configured** —
today nothing changes, and all three surfaces keep working:

- **Telegram bot** — unchanged (long-polling, `admin_ids`/DB role).
- **Mini app** — unchanged (Telegram `initData` HMAC).
- **Flutter app** — unchanged (native `flutter_auth.py` email/password + PyJWT).

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
2. **Native Flutter token** — the current mechanism, unchanged.

Running both at once is the **dual-mode migration window**: embed the Flutter
module in the superapp, have it send superapp tokens, and old native tokens keep
working until every client is migrated. Then delete the native login.

No assumption is made about the superapp beyond "it can hand its webview a signed
JWT" (standard OIDC/JWT). If instead it authenticates via a gateway-injected
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

## Remaining steps at cutover (need superapp specifics)

- **CORS / CSP**: add the superapp webview origin to `_cors_origins` and to the
  `frame-ancestors` CSP in `app/web/main.py` (both are Telegram-only today).
- **`TRUSTED_PROXY_IPS`**: set to the superapp/university gateway IP, or all
  users collapse to one rate-limit bucket.
- **Flutter build**: ship with `--dart-define=API_BASE_URL=https://<prod-host>`
  (release builds now refuse to run without it).
- **Remove native login** once all clients send superapp tokens: delete
  `flutter_auth_router` (register/login) and, if unused elsewhere, the
  `password_hash` column and reset flows.
- **Role provisioning**: decide how superapp roles/groups map to coordinator
  (`admin`) vs club-head (`user`) and set `SUPERAPP_ROLE_CLAIM` /
  `SUPERAPP_ADMIN_ROLE_VALUE` accordingly.
