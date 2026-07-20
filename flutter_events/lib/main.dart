import 'package:flutter/widgets.dart';

import 'app.dart';
import 'core/dev_session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeEventsFeature();
  await ensureDevSession();
  runApp(
    EventsApp(
      onStandaloneSignIn: ensureDevSession,
      onDevelopmentRoleSwitch: cycleDevRole,
    ),
  );
}
