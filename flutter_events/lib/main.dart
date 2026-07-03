import 'package:flutter/widgets.dart';

import 'app.dart';
import 'core/auth_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AuthStore.init();
  runApp(const EventsApp());
}
