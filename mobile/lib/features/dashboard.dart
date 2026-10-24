import 'package:flutter/material.dart';
import '../core/api_client.dart';
import '../core/realtime.dart';
import '../models/models.dart';
import 'shared.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({
    required this.api,
    required this.realtime,
    required this.onTicket,
    required this.onMachine,
    super.key,
  });
  final ApiClient api;
  final TicketRealtime realtime;
  final void Function(int) onTicket, onMachine;
  @override
  Widget build(BuildContext context) => AsyncContent<Json>(
    load: () async => object(await api.request('GET', '/dashboard')),
    events: realtime.events,
    builder: (context, data) => ListView(
      padding: const EdgeInsets.all(20),
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        Text(
          'Visão geral',
          style: Theme.of(
            context,
          ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 6),
        const Text('Sua escola, equipamentos e atendimentos.'),
        const SizedBox(height: 24),
        LayoutBuilder(
          builder: (context, constraints) => GridView.count(
            crossAxisCount: constraints.maxWidth > 550 ? 4 : 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio:
                .95 /
                (MediaQuery.textScalerOf(context).scale(14) / 14).clamp(1, 3),
            children: [
              _metric(
                context,
                'Máquinas',
                data['total_machines'],
                Icons.computer,
                Colors.indigo,
              ),
              _metric(
                context,
                'PCs online',
                data['online_count'],
                Icons.wifi,
                Colors.teal,
              ),
              _metric(
                context,
                'Aguardando',
                integer(data['open_tickets']) -
                    integer(data['in_progress_tickets']),
                Icons.support_agent,
                Colors.red,
              ),
              _metric(
                context,
                'Em atendimento',
                data['in_progress_tickets'],
                Icons.build_outlined,
                Colors.blue,
              ),
              _metric(
                context,
                'Salas urgentes',
                data['urgent_rooms'],
                Icons.priority_high,
                Colors.red,
              ),
              _metric(
                context,
                'Salas em atenção',
                data['attention_rooms'],
                Icons.warning_amber,
                Colors.orange,
              ),
              _metric(
                context,
                'Vistorias pendentes',
                data['pending_inspections'],
                Icons.fact_check_outlined,
                Colors.deepPurple,
              ),
              _metric(
                context,
                'Checkups pendentes',
                data['pending_checkups'],
                Icons.checklist,
                Colors.indigo,
              ),
            ],
          ),
        ),
        const SectionTitle('Chamados recentes'),
        if ((data['recent_tickets'] as List? ?? []).isEmpty)
          const EmptyState('Nenhum chamado registrado.'),
        ...(data['recent_tickets'] as List? ?? []).map((row) {
          final ticket = Ticket.fromJson(object(row));
          return TicketTile(ticket, onTap: () => onTicket(ticket.id));
        }),
        const SectionTitle('Máquinas atualizadas'),
        ...(data['recent_machines'] as List? ?? []).map((row) {
          final machine = Machine.fromJson(object(row));
          return Card(
            child: ListTile(
              leading: const Icon(Icons.computer),
              title: Text(machine.name),
              subtitle: Text(machine.room),
              trailing: StatusBadge(machine.status),
              onTap: () => onMachine(machine.id),
            ),
          );
        }),
        for (final entry in {
          'status_rows': 'Status dos equipamentos',
          'profile_rows': 'Perfis de máquinas',
          'segment_rows': 'Segmentos',
        }.entries)
          if (data[entry.key] is List) ...[
            SectionTitle(entry.value),
            ...(data[entry.key] as List).map((item) {
              final row = object(item);
              return Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(child: Text('${row['label']}')),
                        Text('${row['count']}'),
                      ],
                    ),
                    const SizedBox(height: 7),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: LinearProgressIndicator(
                        value: ((row['percent'] as num? ?? 0) / 100).clamp(
                          0,
                          1,
                        ),
                        minHeight: 7,
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        const SizedBox(height: 20),
        Text(
          '${data['rooms_count'] ?? 0} salas · ${data['closed_tickets'] ?? 0} chamados finalizados',
          textAlign: TextAlign.center,
        ),
      ],
    ),
  );

  Widget _metric(
    BuildContext context,
    String label,
    dynamic value,
    IconData icon,
    Color color,
  ) => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .07),
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: color.withValues(alpha: .12)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, color: color, size: 21),
            const SizedBox(width: 6),
            Expanded(
              child: Align(
                alignment: Alignment.centerRight,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    '${value ?? 0}',
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: color,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
        const Spacer(),
        Text(
          label,
          style: const TextStyle(fontWeight: FontWeight.w500),
          maxLines: 2,
        ),
      ],
    ),
  );
}
