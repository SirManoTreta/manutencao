import 'package:flutter/material.dart';
import '../core/api_client.dart';
import '../core/realtime.dart';
import '../core/session.dart';
import '../models/models.dart';
import 'shared.dart';

class TicketsPage extends StatefulWidget {
  const TicketsPage({
    required this.api,
    required this.realtime,
    required this.onOpen,
    super.key,
  });
  final ApiClient api;
  final TicketRealtime realtime;
  final void Function(int) onOpen;
  @override
  State<TicketsPage> createState() => _TicketsPageState();
}

class _TicketsPageState extends State<TicketsPage> {
  String _status = 'OPEN';
  @override
  Widget build(BuildContext context) => Column(
    children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
        child: SizedBox(
          width: double.infinity,
          child: SegmentedButton<String>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: 'OPEN', label: Text('Abertos')),
              ButtonSegment(value: 'IN_PROGRESS', label: Text('Atendendo')),
              ButtonSegment(value: 'CLOSED', label: Text('Finalizados')),
            ],
            selected: {_status},
            onSelectionChanged: (value) =>
                setState(() => _status = value.first),
          ),
        ),
      ),
      ListenableBuilder(
        listenable: widget.realtime,
        builder: (context, _) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.circle,
                size: 8,
                color: widget.realtime.connected ? Colors.green : Colors.orange,
              ),
              const SizedBox(width: 6),
              Text(
                widget.realtime.connected
                    ? 'Atualizando em tempo real'
                    : 'Reconectando · puxe para atualizar',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
      Expanded(
        child: AsyncContent<List<Json>>(
          key: ValueKey(_status),
          load: () => widget.api.list('/tickets', query: {'status': _status}),
          events: widget.realtime.events,
          builder: (context, rows) => ListView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              if (rows.isEmpty)
                const EmptyState('Nenhum chamado neste status.'),
              ...rows.map((row) {
                final ticket = Ticket.fromJson(row);
                return TicketTile(
                  ticket,
                  onTap: () => widget.onOpen(ticket.id),
                );
              }),
            ],
          ),
        ),
      ),
    ],
  );
}

class TicketDetailPage extends StatefulWidget {
  const TicketDetailPage({
    required this.id,
    required this.session,
    required this.realtime,
    super.key,
  });
  final int id;
  final SessionController session;
  final TicketRealtime realtime;
  @override
  State<TicketDetailPage> createState() => _TicketDetailPageState();
}

class _TicketDetailPageState extends State<TicketDetailPage> {
  final _content = GlobalKey<AsyncContentState<Ticket>>();
  bool _busy = false;
  Future<void> _act(Ticket ticket) async {
    String? diagnosis;
    if (ticket.status == 'IN_PROGRESS') {
      diagnosis = await showDialog<String>(
        context: context,
        builder: (_) => const _DiagnosisDialog(),
      );
      if (diagnosis == null) return;
    }
    if (!mounted) return;
    setState(() => _busy = true);
    try {
      await widget.session.api.request(
        'POST',
        '/tickets/${ticket.id}/${ticket.status == 'OPEN' ? 'take' : 'close'}',
        body: ticket.status == 'OPEN' ? null : {'diagnosis': diagnosis},
      );
      await _content.currentState?.refresh();
    } catch (e) {
      if (mounted) showError(context, e);
      // HTTP 409 means someone else took/closed it. Refresh authoritative state.
      await _content.currentState?.refresh();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text('Chamado #${widget.id}')),
    body: AsyncContent<Ticket>(
      key: _content,
      load: () => widget.session.api.ticket(widget.id),
      events: widget.realtime.events,
      builder: (context, ticket) => ListView(
        padding: const EdgeInsets.all(20),
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: StatusBadge(ticket.status),
          ),
          const SizedBox(height: 20),
          Text(
            ticket.problem,
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 20),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  InfoRow('Computador', ticket.pcName),
                  InfoRow('Sala', ticket.room),
                  InfoRow('Solicitante', ticket.reportedUser),
                  InfoRow('Criado em', displayDate(ticket.createdAt)),
                  InfoRow('Responsável', ticket.assignedBy),
                  if (ticket.assignedAt != null)
                    InfoRow('Assumido em', displayDate(ticket.assignedAt)),
                  if (ticket.closedAt != null) ...[
                    InfoRow('Finalizado por', ticket.closedBy),
                    InfoRow('Finalizado em', displayDate(ticket.closedAt)),
                  ],
                ],
              ),
            ),
          ),
          if (ticket.diagnosis?.isNotEmpty == true) ...[
            const SectionTitle('Diagnóstico técnico'),
            SelectableText(ticket.diagnosis!),
          ],
          if (ticket.diagnostics?.isNotEmpty == true)
            ExpansionTile(
              title: const Text('Diagnóstico enviado pelo PC'),
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: SelectableText(ticket.diagnostics!),
                ),
              ],
            ),
          const SizedBox(height: 28),
          if (ticket.status == 'OPEN' || ticket.status == 'IN_PROGRESS')
            FilledButton.icon(
              onPressed: _busy ? null : () => _act(ticket),
              icon: Icon(
                ticket.status == 'OPEN'
                    ? Icons.handyman_outlined
                    : Icons.task_alt,
              ),
              label: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  _busy
                      ? 'Salvando…'
                      : ticket.status == 'OPEN'
                      ? 'Assumir chamado'
                      : 'Finalizar chamado',
                ),
              ),
            ),
        ],
      ),
    ),
  );
}

class _DiagnosisDialog extends StatefulWidget {
  const _DiagnosisDialog();
  @override
  State<_DiagnosisDialog> createState() => _DiagnosisDialogState();
}

class _DiagnosisDialogState extends State<_DiagnosisDialog> {
  final _controller = TextEditingController();
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Finalizar chamado'),
    content: TextField(
      controller: _controller,
      maxLines: 4,
      maxLength: 10000,
      decoration: const InputDecoration(
        labelText: 'Diagnóstico / solução',
        hintText: 'Descreva o atendimento realizado',
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancelar'),
      ),
      FilledButton(
        onPressed: () => Navigator.pop(context, _controller.text.trim()),
        child: const Text('Finalizar'),
      ),
    ],
  );
}
