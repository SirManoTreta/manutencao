typedef Json = Map<String, dynamic>;

Json object(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};
int integer(dynamic value) =>
    value is num ? value.toInt() : int.tryParse('$value') ?? 0;
bool flag(dynamic value) => value == true || value == 1;

class AppUser {
  const AppUser({
    required this.id,
    required this.username,
    this.isAdmin = false,
    this.isActive = true,
  });
  factory AppUser.fromJson(Json json) => AppUser(
    id: integer(json['id']),
    username: json['username'] as String,
    isAdmin: flag(json['is_admin']),
    isActive: json['is_active'] != false,
  );
  final int id;
  final String username;
  final bool isAdmin;
  final bool isActive;
  Json toJson() => {
    'id': id,
    'username': username,
    'is_admin': isAdmin,
    'is_active': isActive,
  };
}

class Ticket {
  Ticket.fromJson(Json json)
    : id = integer(json['id']),
      pcName = '${json['pc_name'] ?? ''}',
      problem = '${json['problem'] ?? ''}',
      status = '${json['status'] ?? 'OPEN'}',
      room =
          '${json['room_name'] ?? object(json['machine'])['room_name'] ?? 'Não cadastrada'}',
      reportedUser = json['reported_user'] as String?,
      assignedBy = json['assigned_by'] as String?,
      closedBy = json['closed_by'] as String?,
      diagnosis = (json['diagnosis'] ?? json['resolution_note']) as String?,
      diagnostics = json['diagnostics_json']?.toString(),
      createdAt = DateTime.tryParse('${json['created_at']}'),
      assignedAt = DateTime.tryParse('${json['assigned_at']}'),
      closedAt = DateTime.tryParse('${json['closed_at']}');
  final int id;
  final String pcName, problem, status, room;
  final String? reportedUser, assignedBy, closedBy, diagnosis, diagnostics;
  final DateTime? createdAt, assignedAt, closedAt;
}

class Machine {
  Machine.fromJson(Json value) : data = Map.unmodifiable(value);
  final Json data;
  int get id => integer(data['id']);
  String get name => '${data['machine_name'] ?? ''}';
  String get room => '${data['room_name'] ?? ''}';
  String get profile => '${data['profile'] ?? 'A'}';
  String get status => '${data['room_status'] ?? 'OK'}';
  List<Json> get peripherals =>
      (data['peripherals'] as List? ?? []).map(object).toList();
}

class Room {
  Room.fromJson(Json json)
    : name = '${json['room_name']}',
      status = '${json['room_status']}',
      machineCount = integer(json['machine_count']);
  final String name, status;
  final int machineCount;
}

class OnlineComputer {
  OnlineComputer.fromJson(Json json)
    : name = '${json['pc_name']}',
      online = flag(json['is_online']),
      age = integer(json['age_seconds']),
      loginActive = flag(json['login_active']),
      user = json['last_user'] as String?,
      room =
          '${json['room_name'] ?? object(json['machine'])['room_name'] ?? 'Não cadastrado'}';
  final String name, room;
  final bool online, loginActive;
  final int age;
  final String? user;
}

const statusLabels = {
  'OK': 'Tudo OK',
  'ATTENTION': 'Atenção',
  'URGENT': 'Urgente',
  'OPEN': 'Aberto',
  'IN_PROGRESS': 'Em atendimento',
  'CLOSED': 'Finalizado',
};

const peripheralLabels = {
  'MOUSE': 'Mouse',
  'TECLADO': 'Teclado',
  'TELA': 'Tela',
  'AMPLIFICADOR': 'Amplificador',
  'MICROFONE': 'Microfone',
  'CABO_MICROFONE': 'Cabo de microfone',
  'CABO_RCA': 'Cabo RCA',
  'CAMERA_EAD': 'Câmera EAD',
  'PROJETOR': 'Projetor',
  'CONTROLE_PROJETOR': 'Controle do projetor',
  'ESTOJO_CANETAS': 'Estojo de canetas',
  'CANETAS_PROJETOR': 'Canetas do projetor',
  'TELA_INTERATIVA': 'Tela interativa',
  'CONTROLE_TELA': 'Controle da tela',
  'CANETA_TELA_INTERATIVA': 'Caneta da tela interativa',
  'CAIXA_SOM': 'Caixa de som',
  'FONE_OUVIDO': 'Fone de ouvido',
  'WEBCAM': 'Webcam',
};

List<String> peripheralCodes(String profile) => [
  'MOUSE',
  'TECLADO',
  'TELA',
  if (profile == 'C') ...[
    'CAIXA_SOM',
    'FONE_OUVIDO',
    'WEBCAM',
  ] else ...[
    'AMPLIFICADOR',
    'MICROFONE',
    'CABO_MICROFONE',
    'CABO_RCA',
    'CAMERA_EAD',
    if (profile == 'A') ...[
      'PROJETOR',
      'CONTROLE_PROJETOR',
      'ESTOJO_CANETAS',
      'CANETAS_PROJETOR',
    ] else ...[
      'TELA_INTERATIVA',
      'CONTROLE_TELA',
      'CANETA_TELA_INTERATIVA',
    ],
  ],
];
