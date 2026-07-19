import 'package:flutter/widgets.dart';

import 'app.dart';
import 'core/auth_store.dart';
import 'core/cache_store.dart';
import 'core/dev_session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AuthStore.init();
  await CacheStore.init();
  if (DevSessionConfig.isEnabled) {
    await ensureDevSession();
  } else {
    await AuthStore.clear();
  }
  runApp(
    EventsApp(
      onStandaloneSignIn: DevSessionConfig.isEnabled ? ensureDevSession : null,
      onDevelopmentRoleSwitch: DevSessionConfig.isEnabled ? cycleDevRole : null,
    ),
  );
}
