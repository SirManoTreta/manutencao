import 'dart:async';
import 'package:flutter/material.dart';
import '../core/api_client.dart';
import '../models/models.dart';
import 'shared.dart';

class OnlinePage extends StatefulWidget {
  const OnlinePage({required this.api, super.key});
  final ApiClient api;
  @override
  State<OnlinePage> createState() => _OnlinePageState();
}

class _OnlinePageState extends State<OnlinePage> with WidgetsBindingObserver {
  final _ticks = StreamController<void>.broadcast();
  Timer? _timer;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _start();
  }

  void _start() {
    _timer?.cancel();
    _timer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _ticks.add(null),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _ticks.add(null);
      _start();
    } else {
      _timer?.cancel();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _ticks.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Computadores online')),
    body: AsyncContent<List<Json>>(
      load: () => widget.api.list('/online'),
      events: _ticks.stream,
      builder: (context, rows) => ListView(
        padding: const EdgeInsets.all(12),
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          const Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'Atualização automática a cada 10 segundos. O heartbeat informa presença e sessão do PC.',
            ),
          ),
          if (rows.isEmpty)
            const EmptyState('Nenhum heartbeat recebido até agora.'),
          ...rows.map((row) {
            final pc = OnlineComputer.fromJson(row);
            return Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.circle,
                          color: pc.online ? Colors.green : Colors.grey,
                          size: 12,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            pc.name,
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                        ),
                        Text(pc.online ? 'Online' : 'Offline'),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(pc.room),
                    const SizedBox(height: 6),
                    Text(
                      pc.loginActive ? 'Usuário: ${pc.user}' : 'Tela de login',
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Heartbeat: ${pc.age}s atrás',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            );
          }),
        ],
      ),
    ),
  );
}
