import 'package:flutter/material.dart';
import '../core/api_client.dart';
import '../models/models.dart';
import 'machines.dart';
import 'shared.dart';

class RoomsPage extends StatelessWidget {
  const RoomsPage({required this.api, super.key});
  final ApiClient api;
  @override
  Widget build(BuildContext context) => AsyncContent<List<Json>>(
    load: () => api.list('/rooms'),
    builder: (context, rows) => ListView(
      padding: const EdgeInsets.all(12),
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        if (rows.isEmpty)
          const EmptyState('Cadastre uma máquina para criar sua sala.'),
        ...rows.map((row) {
          final room = Room.fromJson(row);
          return Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(16),
              leading: const Icon(Icons.meeting_room_outlined),
              title: Text(room.name),
              subtitle: Text('${room.machineCount} máquinas'),
              trailing: StatusBadge(room.status),
              onTap: () async {
                await Navigator.push<void>(
                  context,
                  MaterialPageRoute(
                    builder: (_) => RoomDetailPage(api: api, room: room),
                  ),
                );
                if (context.mounted) {
                  context
                      .findAncestorStateOfType<AsyncContentState<List<Json>>>()
                      ?.refresh();
                }
              },
            ),
          );
        }),
      ],
    ),
  );
}

class RoomDetailPage extends StatefulWidget {
  const RoomDetailPage({required this.api, required this.room, super.key});
  final ApiClient api;
  final Room room;
  @override
  State<RoomDetailPage> createState() => _RoomDetailPageState();
}

class _RoomDetailPageState extends State<RoomDetailPage> {
  final _content = GlobalKey<AsyncContentState<List<Json>>>();
  late String _status = widget.room.status;
  bool _busy = false;
  Future<List<Json>> _load() async {
    final rows = await widget.api.list(
      '/rooms/machines',
      query: {'room_name': widget.room.name},
    );
    const rank = {'OK': 0, 'ATTENTION': 1, 'URGENT': 2};
    var worst = 'OK';
    for (final row in rows) {
      final status = '${row['room_status'] ?? 'OK'}';
      if ((rank[status] ?? 0) > rank[worst]!) worst = status;
    }
    if (mounted && _status != worst) setState(() => _status = worst);
    return rows;
  }

  Future<void> _change(String status) async {
    if (status == _status) return;
    setState(() => _busy = true);
    try {
      await widget.api.request(
        'PATCH',
        '/rooms/status',
        body: {'room_name': widget.room.name, 'room_status': status},
      );
      if (mounted) setState(() => _status = status);
      await _content.currentState?.refresh();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.room.name)),
    body: Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(20),
          child: DropdownButtonFormField<String>(
            key: ValueKey(_status),
            initialValue: _status,
            decoration: const InputDecoration(
              labelText: 'Status de todas as máquinas da sala',
            ),
            items: ['OK', 'ATTENTION', 'URGENT']
                .map(
                  (s) =>
                      DropdownMenuItem(value: s, child: Text(statusLabels[s]!)),
                )
                .toList(),
            onChanged: _busy ? null : (status) => _change(status!),
          ),
        ),
        if (_busy) const LinearProgressIndicator(),
        Expanded(
          child: AsyncContent<List<Json>>(
            key: _content,
            load: _load,
            builder: (context, rows) => ListView(
              padding: const EdgeInsets.all(12),
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                if (rows.isEmpty)
                  const EmptyState('Nenhuma máquina nesta sala.'),
                ...rows.map((row) {
                  final machine = Machine.fromJson(row);
                  return Card(
                    child: ListTile(
                      leading: const Icon(Icons.computer),
                      title: Text(machine.name),
                      subtitle: Text(
                        '${machine.data['ip']} · Perfil ${machine.profile}',
                      ),
                      trailing: StatusBadge(machine.status),
                      onTap: () async {
                        await Navigator.push<void>(
                          context,
                          MaterialPageRoute(
                            builder: (_) => MachineDetailPage(
                              api: widget.api,
                              id: machine.id,
                            ),
                          ),
                        );
                        _content.currentState?.refresh();
                      },
                    ),
                  );
                }),
              ],
            ),
          ),
        ),
      ],
    ),
  );
}
