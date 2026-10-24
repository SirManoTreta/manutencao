import 'dart:async';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/session.dart';
import 'core/api_client.dart';
import 'core/push_service.dart';
import 'core/realtime.dart';
import 'features/dashboard.dart';
import 'features/login.dart';
import 'features/machines.dart';
import 'features/online.dart';
import 'features/rooms.dart';
import 'features/shared.dart';
import 'features/tickets.dart';
import 'features/users.dart';

class MaintenanceApp extends StatefulWidget {
  const MaintenanceApp({
    required this.session,
    required this.push,
    required this.realtime,
    super.key,
  });
  final SessionController session;
  final PushService push;
  final TicketRealtime realtime;
  @override
  State<MaintenanceApp> createState() => _MaintenanceAppState();
}

class _MaintenanceAppState extends State<MaintenanceApp>
    with WidgetsBindingObserver {
  var _navigator = GlobalKey<NavigatorState>();
  bool _pendingScheduled = false;
  bool _authenticated = false;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.session.addListener(_sessionChanged);
    widget.push.pendingTicket.addListener(_openPendingTicket);
    _sessionChanged();
  }

  void _sessionChanged() {
    final authenticated = widget.session.authenticated;
    if (_authenticated == authenticated) return;
    _authenticated = authenticated;
    // A new navigator prevents old private routes surviving logout/401.
    _navigator = GlobalKey<NavigatorState>();
    if (authenticated) {
      widget.realtime.start();
      unawaited(widget.push.enable());
      _openPendingTicket();
    } else {
      widget.realtime.stop();
      unawaited(widget.push.unregister());
    }
  }

  void _openPendingTicket() {
    final id = widget.push.pendingTicket.value;
    if (id == null || !widget.session.authenticated || _pendingScheduled) {
      return;
    }
    if (!widget.push.pendingOriginMatchesServer) {
      widget.push.discardPendingTicket();
      return;
    }
    _pendingScheduled = true;
    final generation = widget.session.generation;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pendingScheduled = false;
      if (!mounted ||
          !widget.session.authenticated ||
          widget.session.generation != generation ||
          widget.push.pendingTicket.value != id ||
          !widget.push.pendingOriginMatchesServer ||
          _navigator.currentState == null) {
        if (mounted && widget.session.authenticated) _openPendingTicket();
        return;
      }
      widget.push.discardPendingTicket();
      _navigator.currentState!.push(
        MaterialPageRoute<void>(
          builder: (_) => TicketDetailPage(
            id: id,
            session: widget.session,
            realtime: widget.realtime,
          ),
        ),
      );
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!widget.session.authenticated) return;
    if (state == AppLifecycleState.resumed) {
      widget.realtime.start();
      unawaited(widget.push.enable());
    } else if (state == AppLifecycleState.paused) {
      widget.realtime.stop();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.session.removeListener(_sessionChanged);
    widget.push.pendingTicket.removeListener(_openPendingTicket);
    widget.realtime.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.session,
    builder: (context, _) => MaterialApp(
      key: ValueKey(widget.session.generation),
      navigatorKey: _navigator,
      title: 'Manutenção TI',
      debugShowCheckedModeBanner: false,
      locale: const Locale('pt', 'BR'),
      supportedLocales: const [Locale('pt', 'BR')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3057B3)),
        scaffoldBackgroundColor: const Color(0xFFF6F8FC),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFFF6F8FC),
          centerTitle: false,
        ),
        cardTheme: CardThemeData(
          elevation: 0,
          color: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: Color(0xFFD5DDEC)),
          ),
        ),
        navigationBarTheme: const NavigationBarThemeData(
          backgroundColor: Colors.white,
        ),
      ),
      home: widget.session.authenticated
          ? HomeShell(
              session: widget.session,
              push: widget.push,
              realtime: widget.realtime,
            )
          : LoginPage(session: widget.session),
    ),
  );
}

class HomeShell extends StatefulWidget {
  const HomeShell({
    required this.session,
    required this.push,
    required this.realtime,
    super.key,
  });
  final SessionController session;
  final PushService push;
  final TicketRealtime realtime;
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _selected = 0;
  void _ticket(int id) => Navigator.push<void>(
    context,
    MaterialPageRoute(
      builder: (_) => TicketDetailPage(
        id: id,
        session: widget.session,
        realtime: widget.realtime,
      ),
    ),
  );
  void _machine(int id) => Navigator.push<void>(
    context,
    MaterialPageRoute(
      builder: (_) => MachineDetailPage(id: id, api: widget.session.api),
    ),
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        ['Manutenção TI', 'Chamados', 'Máquinas', 'Salas', 'Mais'][_selected],
      ),
      actions: [
        IconButton(
          tooltip: 'Perfil e configurações',
          onPressed: () => Navigator.push<void>(
            context,
            MaterialPageRoute(
              builder: (_) =>
                  ProfilePage(session: widget.session, push: widget.push),
            ),
          ),
          icon: const Icon(Icons.account_circle_outlined),
        ),
      ],
    ),
    body: IndexedStack(
      index: _selected,
      children: [
        DashboardPage(
          api: widget.session.api,
          realtime: widget.realtime,
          onTicket: _ticket,
          onMachine: _machine,
        ),
        TicketsPage(
          api: widget.session.api,
          realtime: widget.realtime,
          onOpen: _ticket,
        ),
        MachinesPage(api: widget.session.api),
        RoomsPage(api: widget.session.api),
        MorePage(session: widget.session, push: widget.push),
      ],
    ),
    bottomNavigationBar: NavigationBar(
      selectedIndex: _selected,
      onDestinationSelected: (value) => setState(() => _selected = value),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.space_dashboard_outlined),
          selectedIcon: Icon(Icons.space_dashboard),
          label: 'Início',
        ),
        NavigationDestination(
          icon: Icon(Icons.support_agent_outlined),
          selectedIcon: Icon(Icons.support_agent),
          label: 'Chamados',
        ),
        NavigationDestination(
          icon: Icon(Icons.computer_outlined),
          selectedIcon: Icon(Icons.computer),
          label: 'Máquinas',
        ),
        NavigationDestination(
          icon: Icon(Icons.meeting_room_outlined),
          selectedIcon: Icon(Icons.meeting_room),
          label: 'Salas',
        ),
        NavigationDestination(icon: Icon(Icons.more_horiz), label: 'Mais'),
      ],
    ),
  );
}

class MorePage extends StatelessWidget {
  const MorePage({required this.session, required this.push, super.key});
  final SessionController session;
  final PushService push;
  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      const SectionTitle('Seu dia a dia'),
      _item(
        context,
        Icons.wifi,
        'Computadores online',
        'Heartbeats e usuários conectados',
        OnlinePage(api: session.api),
      ),
      _item(
        context,
        Icons.fact_check_outlined,
        'Vistorias pendentes',
        'Máquinas que precisam de vistoria',
        Scaffold(
          appBar: AppBar(title: const Text('Vistorias pendentes')),
          body: MachinesPage(
            api: session.api,
            initialFilters: const {'inspected': 'false'},
          ),
        ),
      ),
      _item(
        context,
        Icons.checklist,
        'Checkups pendentes',
        'Máquinas que precisam de checkup',
        Scaffold(
          appBar: AppBar(title: const Text('Checkups pendentes')),
          body: MachinesPage(
            api: session.api,
            initialFilters: const {'checkup_done': 'false'},
          ),
        ),
      ),
      if (session.user?.isAdmin == true)
        _item(
          context,
          Icons.manage_accounts_outlined,
          'Usuários',
          'Contas e permissões',
          UsersPage(session: session),
        ),
      const SectionTitle('Conta'),
      _item(
        context,
        Icons.settings_outlined,
        'Perfil e configurações',
        session.api.baseUrl,
        ProfilePage(session: session, push: push),
      ),
    ],
  );
  Widget _item(
    BuildContext context,
    IconData icon,
    String title,
    String subtitle,
    Widget page,
  ) => Card(
    child: ListTile(
      leading: Icon(icon),
      title: Text(title),
      subtitle: Text(subtitle),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => Navigator.push<void>(
        context,
        MaterialPageRoute(builder: (_) => page),
      ),
    ),
  );
}

class ProfilePage extends StatefulWidget {
  const ProfilePage({required this.session, required this.push, super.key});
  final SessionController session;
  final PushService push;
  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  bool _busy = false;
  bool _copying = false;
  Future<void> _copyDebugToken() async {
    setState(() => _copying = true);
    try {
      final token = await widget.push.getDebugToken();
      if (!mounted) return;
      if (token == null || token.isEmpty) {
        throw const ApiException(
          'Token indisponível ou sessão alterada. Tente novamente.',
        );
      }
      await Clipboard.setData(ClipboardData(text: token));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Token de teste copiado. Cole somente no Firebase Console e mantenha privado.',
            ),
          ),
        );
      }
    } catch (error) {
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _copying = false);
    }
  }

  Future<void> _logout() async {
    setState(() => _busy = true);
    await widget.push.unregister();
    await widget.session.logout();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Perfil e configurações')),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const CircleAvatar(
          radius: 36,
          child: Icon(Icons.person_outline, size: 36),
        ),
        const SizedBox(height: 20),
        Text(
          widget.session.user?.username ?? '',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        Text(
          widget.session.user?.isAdmin == true ? 'Administrador' : 'Técnico',
          textAlign: TextAlign.center,
        ),
        const SectionTitle('Servidor'),
        SelectableText(widget.session.api.baseUrl),
        const SizedBox(height: 8),
        const Text(
          'Para alterar servidor, encerre a sessão e edite o endereço na tela de entrada.',
        ),
        if (widget.session.notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Text(widget.session.notice!),
          ),
        const SectionTitle('Notificações'),
        ListenableBuilder(
          listenable: widget.push,
          builder: (context, _) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.push.status),
              if (widget.push.deviceName != null)
                InfoRow('Dispositivo', widget.push.deviceName),
              if (widget.push.registeredAt != null)
                InfoRow('Registrado em', displayDate(widget.push.registeredAt)),
              if (widget.push.backendStatus != null) ...[
                InfoRow(
                  'Envio no servidor',
                  widget.push.backendStatus!.enabled
                      ? 'Habilitado'
                      : 'Desativado',
                ),
                InfoRow(
                  'Credencial informada',
                  widget.push.backendStatus!.credentialsConfigured,
                ),
                InfoRow(
                  'Dispositivos ativos nesta conta',
                  widget.push.backendStatus!.activeDevices,
                ),
                const Text(
                  'Credencial informada não comprova validade ou entrega de push.',
                  style: TextStyle(fontSize: 12),
                ),
              ],
              if (widget.push.backendStatusNotice != null)
                Text(widget.push.backendStatusNotice!),
              const SizedBox(height: 16),
              FilledButton.tonalIcon(
                onPressed: widget.push.available ? widget.push.enable : null,
                icon: const Icon(Icons.notifications_active_outlined),
                label: const Text('Ativar / verificar notificações'),
              ),
              if (kDebugMode) ...[
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed:
                      widget.push.available &&
                          widget.push.permissionGranted &&
                          !_copying &&
                          !_busy
                      ? _copyDebugToken
                      : null,
                  icon: const Icon(Icons.copy_outlined),
                  label: Text(_copying ? 'Copiando…' : 'Copiar token de teste'),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Somente debug: use no Firebase Console. Não publique o token.',
                  style: TextStyle(fontSize: 12),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 32),
        OutlinedButton.icon(
          onPressed: _busy ? null : _logout,
          icon: const Icon(Icons.logout),
          label: Text(_busy ? 'Encerrando…' : 'Sair / trocar servidor'),
        ),
        const SizedBox(height: 24),
        const Text(
          'Manutenção TI · Cliente do sistema escolar',
          textAlign: TextAlign.center,
        ),
      ],
    ),
  );
}
