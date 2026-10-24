import 'package:firebase_core/firebase_core.dart';

/// Android/iOS use the native public configuration produced by FlutterFire:
/// google-services.json (Gradle) and GoogleService-Info.plist (Runner target).
/// No import of a missing generated file and no fabricated Firebase project.
Future<FirebaseApp> initializeMaintenanceFirebase() async {
  if (Firebase.apps.isNotEmpty) return Firebase.app();
  return Firebase.initializeApp();
}
