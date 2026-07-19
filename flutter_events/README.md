# Events Flutter feature

Flutter organizer and coordinator UI for creating, reviewing, and managing
events. The standalone executable is a development host for the same feature
that will be mounted inside Jas Wallet.

## Standalone development

Run the Android development host with:

```sh
flutter run -d emulator-5554
```

Debug builds enable the shared development accounts by default. Disable them
when testing the host-session boundary:

```sh
flutter run \
  --dart-define=ENABLE_STANDALONE_DEV_ACCESS=false \
  --dart-define=API_BASE_URL=https://events.example.edu
```

`ENABLE_STANDALONE_DEV_ACCESS` is effective only in debug builds. Profile and
release builds cannot activate shared test login or role switching, even when
the define is set. The existing `TEST_USER_*` and `TEST_ADMIN_*` defines remain
available for local development and must never contain production credentials.
The backend must also run with `LOG_LEVEL=DEBUG` and
`FLUTTER_NATIVE_AUTH_ENABLED=true`; native login and native tokens are rejected
otherwise.

Release builds require an HTTPS API endpoint:

```sh
flutter build apk --release \
  --dart-define=API_BASE_URL=https://events.example.edu
```

## Jas Wallet integration contract

Jas Wallet mounts `EventsFeature` from `lib/app.dart` inside its authenticated
tab shell and supplies only its current bearer token:

```dart
EventsFeature(
  session: EventsHostSession(accessToken: jasWalletAccessToken),
  onSessionExpired: refreshJasWalletSession,
)
```

The feature initializes its own stores and calls
`GET /api/flutter/auth/session` before rendering event data. That endpoint verifies
the token, resolves or provisions the local Events identity, and returns the
server-authoritative local user ID and role. Jas Wallet must replace the
`EventsHostSession` with a fresh token after `onSessionExpired`; it must not pass
or infer an Events role on the client.

The host owns authentication, top-level navigation, app lifecycle, theme,
locale, and release environment configuration. `EventsFeature` owns only its
tab content and internal feature navigation. A `MaterialApp`/`Navigator` must
already exist above it. The feature never logs the bearer token and does not
need the Jas Wallet signing key. Host tokens stay in memory and are never
written to the feature's `SharedPreferences` storage.

`EventsApp` and `lib/main.dart` are standalone-development infrastructure. They
must not be embedded in Jas Wallet. The optional development role-switch
callback is injected by the standalone host and is absent in production.

Current dependencies supplied by the feature package:

- Flutter Material runtime
- the local `app_ui` package
- HTTPS access to the Events API
- a Jas Wallet bearer token accepted by the configured backend bridge
- a callback that refreshes or replaces an expired host session

The backend token bridge is documented in
[`../backend/SUPERAPP_BRIDGE.md`](../backend/SUPERAPP_BRIDGE.md).

## Verification

```sh
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build apk --debug
```
