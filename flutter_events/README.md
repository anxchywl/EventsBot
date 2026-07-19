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

Release builds require an HTTPS API endpoint:

```sh
flutter build apk --release \
  --dart-define=API_BASE_URL=https://events.example.edu
```

## Jas Wallet integration contract

Jas Wallet should mount `EventsFeature` from `lib/app.dart` inside its own
authenticated navigation shell. It must initialize the Events session before
mounting the widget and provide a backend bearer token accepted by the existing
SuperApp bridge. The host owns authentication, top-level navigation, app
lifecycle, and release environment configuration.

The widget boundary is ready, but the production session adapter is not yet
complete. The backend accepts a configured Jas Wallet JWT, but it does not
currently expose an authenticated bootstrap endpoint returning the resolved
local Events user ID and role. Add that endpoint before embedding, then have the
adapter initialize `AuthStore` and `CacheStore` from its response. Do not infer
admin access from client-provided role data; the backend remains authoritative.

`EventsApp` and `lib/main.dart` are standalone-development infrastructure. They
must not be embedded in Jas Wallet. The optional development role-switch
callback is injected by the standalone host and is absent in production.

Current dependencies supplied by the feature package:

- Flutter Material runtime
- the local `app_ui` package
- HTTPS access to the Events API
- a valid user or admin session established by the future host adapter before
  `EventsFeature` is mounted

The backend token bridge is documented in
[`../backend/SUPERAPP_BRIDGE.md`](../backend/SUPERAPP_BRIDGE.md).

## Verification

```sh
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build apk --debug
```
