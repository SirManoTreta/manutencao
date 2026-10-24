import 'package:flutter/material.dart';
import 'app.dart';
import 'core/api_client.dart';
import 'core/session.dart';
import 'core/push_service.dart';
import 'core/realtime.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final api = ApiClient();
  final session = SessionController(api, SecureSessionStorage());
  final push = PushService(api);
  await session.restore();
  await push.initialize();
  runApp(
    MaintenanceApp(session: session, push: push, realtime: TicketRealtime(api)),
  );
}
