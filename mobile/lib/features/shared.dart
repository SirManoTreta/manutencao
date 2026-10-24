import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../core/api_client.dart';
import '../models/models.dart';

String displayDate(DateTime? value) => value == null
    ? '—'
    : DateFormat('dd/MM/yyyy HH:mm').format(value.toLocal());
void showError(BuildContext context, Object error) =>
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          error is ApiException
              ? error.message
              : 'Falha ao executar operação. Tente novamente.',
        ),
      ),
    );

Future<bool> confirm(
  BuildContext context,
  String title,
  String message,
) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirmar'),
          ),
        ],
      ),
    ) ??
    false;

class StatusBadge extends StatelessWidget {
  const StatusBadge(this.status, {super.key});
  final String status;
  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'URGENT' || 'OPEN' => Colors.red.shade700,
      'ATTENTION' => Colors.orange.shade800,
      'IN_PROGRESS' => Colors.blue.shade700,
      _ => Colors.green.shade700,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .10),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        statusLabels[status] ?? status,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.w600,
          fontSize: 12,
        ),
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key});
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 24, bottom: 12),
    child: Text(
      text,
      style: Theme.of(
        context,
      ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
    ),
  );
}

class InfoRow extends StatelessWidget {
  const InfoRow(this.label, this.value, {super.key});
  final String label;
  final Object? value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 132,
          child: Text(
            label,
            style: TextStyle(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ),
        Expanded(
          child: SelectableText(
            value == null || value == ''
                ? '—'
                : value is bool
                ? value == true
                      ? 'Sim'
                      : 'Não'
                : '$value',
          ),
        ),
      ],
    ),
  );
}

class EmptyState extends StatelessWidget {
  const EmptyState(this.text, {super.key});
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 64, horizontal: 20),
    child: Column(
      children: [
        Icon(
          Icons.inbox_outlined,
          size: 48,
          color: Theme.of(context).colorScheme.outline,
        ),
        const SizedBox(height: 16),
        Text(text, textAlign: TextAlign.center),
      ],
    ),
  );
}

/// Keeps refresh/error/loading behavior identical across all server-backed pages.
class AsyncContent<T> extends StatefulWidget {
  const AsyncContent({
    super.key,
    required this.load,
    required this.builder,
    this.events,
  });
  final Future<T> Function() load;
  final Widget Function(BuildContext, T) builder;
  final Stream<dynamic>? events;
  @override
  State<AsyncContent<T>> createState() => AsyncContentState<T>();
}

class AsyncContentState<T> extends State<AsyncContent<T>> {
  late Future<T> _future;
  dynamic _subscription;
  @override
  void initState() {
    super.initState();
    _future = widget.load();
    _listen();
  }

  void _listen() {
    _subscription = widget.events?.listen((_) {
      if (mounted) refresh();
    });
  }

  @override
  void didUpdateWidget(covariant AsyncContent<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.events != widget.events) {
      _subscription?.cancel();
      _listen();
    }
  }

  Future<void> refresh() async {
    final next = widget.load();
    setState(() {
      _future = next;
    });
    try {
      await next;
    } catch (_) {
      /* FutureBuilder renders failure. */
    }
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<T>(
    future: _future,
    builder: (context, snapshot) {
      if (snapshot.connectionState != ConnectionState.done) {
        return const Center(child: CircularProgressIndicator());
      }
      if (snapshot.hasError) {
        return Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.wifi_off, size: 42),
                const SizedBox(height: 16),
                Text('${snapshot.error}', textAlign: TextAlign.center),
                const SizedBox(height: 16),
                FilledButton.tonal(
                  onPressed: refresh,
                  child: const Text('Tentar novamente'),
                ),
              ],
            ),
          ),
        );
      }
      return RefreshIndicator(
        onRefresh: refresh,
        child: widget.builder(context, snapshot.data as T),
      );
    },
  );
}

class TicketTile extends StatelessWidget {
  const TicketTile(this.ticket, {required this.onTap, super.key});
  final Ticket ticket;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Card(
    child: InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '#${ticket.id} · ${ticket.pcName}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                StatusBadge(ticket.status),
              ],
            ),
            const SizedBox(height: 10),
            Text(ticket.problem, maxLines: 3, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 12),
            Text(
              '${ticket.room} · ${displayDate(ticket.createdAt)}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    ),
  );
}
