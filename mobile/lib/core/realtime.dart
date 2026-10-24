import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'api_client.dart';

class TicketRealtime extends ChangeNotifier {
  TicketRealtime(this.api);
  final ApiClient api;
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get events => _events.stream;
  WebSocket? _socket;
  Timer? _retry;
  int _attempt = 0;
  int _generation = 0;
  bool _running = false;
  bool connected = false;

  void start() {
    if (_running || api.token == null) return;
    _running = true;
    _connect(_generation);
  }

  Future<void> _connect(int generation) async {
    if (!_running || generation != _generation || api.token == null) return;
    try {
      final uri = Uri.parse('${api.baseUrl}/ws/v1/tickets');
      final socket = await WebSocket.connect(
        uri.replace(scheme: uri.scheme == 'https' ? 'wss' : 'ws').toString(),
        headers: {'Authorization': 'Bearer ${api.token}'},
      ).timeout(const Duration(seconds: 12));
      if (!_running || generation != _generation) {
        await socket.close();
        return;
      }
      _socket = socket;
      socket.pingInterval = const Duration(seconds: 25);
      connected = true;
      _attempt = 0;
      notifyListeners();
      _events.add({'type': 'connected'});
      socket.listen(
        (data) {
          try {
            final message = jsonDecode('$data');
            if (message is Map &&
                [
                  'ticket_created',
                  'ticket_taken',
                  'ticket_closed',
                ].contains(message['type'])) {
              _events.add(Map<String, dynamic>.from(message));
            }
          } on FormatException {
            /* Ignore heartbeat/non-JSON frames. */
          }
        },
        onDone: () => _disconnected(generation),
        onError: (_) => _disconnected(generation),
        cancelOnError: true,
      );
    } catch (_) {
      _disconnected(generation);
    }
  }

  void _disconnected(int generation) {
    if (generation != _generation) return;
    connected = false;
    notifyListeners();
    if (!_running || _retry?.isActive == true) return;
    final seconds = (1 << _attempt.clamp(0, 5));
    _attempt++;
    _retry = Timer(Duration(seconds: seconds), () => _connect(generation));
  }

  void stop() {
    _running = false;
    _generation++;
    _retry?.cancel();
    _socket?.close();
    _socket = null;
    connected = false;
    notifyListeners();
  }

  @override
  void dispose() {
    stop();
    _events.close();
    super.dispose();
  }
}
