import 'package:flutter/widgets.dart';

import 'app.dart';
import 'core/auth_store.dart';
import 'core/cache_store.dart';
import 'core/dev_session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AuthStore.init();
  await CacheStore.init();
  // No login screen: sign into the shared test account if there is no session.
  await ensureDevSession();
  runApp(const EventsApp());
}
