import 'dart:convert';

/// Only this event is allowed to open a ticket or produce a foreground alert.
/// FCM data values are strings. Keep the old event type during server upgrades.
class TicketNotification {
  const TicketNotification({
    required this.ticketId,
    this.pcName,
    this.roomName,
    this.problem,
  });
  final int ticketId;
  final String? pcName, roomName, problem;

  static TicketNotification? tryParse(Map<String, dynamic> data) {
    if (!['new_ticket', 'ticket_created'].contains(data['type'])) return null;
    final rawId = data['ticket_id'];
    if (rawId is! String || !RegExp(r'^[1-9][0-9]{0,18}$').hasMatch(rawId)) {
      return null;
    }
    final id = int.tryParse(rawId);
    if (id == null || id <= 0) return null;
    String? optionalText(String key) {
      final value = data[key];
      return value is String && value.trim().isNotEmpty ? value.trim() : null;
    }

    return TicketNotification(
      ticketId: id,
      pcName: optionalText('pc_name'),
      roomName: optionalText('room_name'),
      problem: optionalText('problem'),
    );
  }

  static TicketNotification? fromLocalPayload(String? payload) {
    if (payload == null || payload.length > 10000) return null;
    try {
      final data = jsonDecode(payload);
      if (data is! Map<String, dynamic>) return null;
      return tryParse(data);
    } on FormatException {
      return null;
    }
  }

  String toLocalPayload() =>
      jsonEncode({'type': 'new_ticket', 'ticket_id': '$ticketId'});
  String get fallbackBody => [
    if (roomName != null) 'Sala: $roomName',
    if (pcName != null) 'PC: $pcName',
    if (problem != null) 'Problema: $problem',
    if (roomName == null && pcName == null && problem == null)
      'Chamado #$ticketId aguardando atendimento.',
  ].join('\n');
}
