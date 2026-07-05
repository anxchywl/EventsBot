import 'package:flutter/widgets.dart';

import 'app.dart';
import 'core/auth_store.dart';
import 'core/cache_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AuthStore.init();
  await CacheStore.init();
  runApp(const EventsApp());
}
