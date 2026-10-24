import 'package:flutter/material.dart';
import '../core/session.dart';
import '../models/models.dart';
import 'shared.dart';

class UsersPage extends StatefulWidget {
  const UsersPage({required this.session, super.key});
  final SessionController session;
  @override
  State<UsersPage> createState() => _UsersPageState();
}

class _UsersPageState extends State<UsersPage> {
  final _content = GlobalKey<AsyncContentState<List<Json>>>();
  Future<void> _edit([AppUser? user]) async {
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => UserFormPage(session: widget.session, user: user),
      ),
    );
    if (saved == true) _content.currentState?.refresh();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Usuários')),
    body: widget.session.user?.isAdmin != true
        ? const Center(child: Text('Acesso restrito a administradores.'))
        : AsyncContent<List<Json>>(
            key: _content,
            load: () => widget.session.api.list('/users'),
            builder: (context, rows) => ListView(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 96),
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                ...rows.map((row) {
                  final user = AppUser.fromJson(row);
                  return Card(
                    child: ListTile(
                      leading: Icon(
                        user.isAdmin
                            ? Icons.admin_panel_settings_outlined
                            : Icons.person_outline,
                      ),
                      title: Text(user.username),
                      subtitle: Text(
                        '${user.isAdmin ? 'Administrador' : 'Técnico'} · ${user.isActive ? 'Ativo' : 'Inativo'}',
                      ),
                      trailing: const Icon(Icons.edit_outlined),
                      onTap: () => _edit(user),
                    ),
                  );
                }),
              ],
            ),
          ),
    floatingActionButton: widget.session.user?.isAdmin != true
        ? null
        : FloatingActionButton.extended(
            onPressed: _edit,
            icon: const Icon(Icons.person_add_alt),
            label: const Text('Usuário'),
          ),
  );
}

class UserFormPage extends StatefulWidget {
  const UserFormPage({required this.session, this.user, super.key});
  final SessionController session;
  final AppUser? user;
  @override
  State<UserFormPage> createState() => _UserFormPageState();
}

class _UserFormPageState extends State<UserFormPage> {
  final _form = GlobalKey<FormState>();
  late final _username = TextEditingController(text: widget.user?.username);
  final _password = TextEditingController();
  late bool _admin = widget.user?.isAdmin ?? false,
      _active = widget.user?.isActive ?? true;
  bool _busy = false;
  bool get _self => widget.user?.id == widget.session.user?.id;
  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await widget.session.api.request(
        widget.user == null ? 'POST' : 'PUT',
        '/users${widget.user == null ? '' : '/${widget.user!.id}'}',
        body: {
          'username': _username.text.trim(),
          if (_password.text.isNotEmpty) 'password': _password.text,
          'is_admin': _admin,
          if (widget.user != null) 'is_active': _active,
        },
      );
      if (_self) await widget.session.restore();
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _deactivate() async {
    if (!await confirm(
      context,
      'Desativar usuário?',
      'O usuário perderá acesso ao site e ao aplicativo. Seu histórico será preservado.',
    )) {
      return;
    }
    if (!mounted) return;
    setState(() => _busy = true);
    try {
      await widget.session.api.request('DELETE', '/users/${widget.user!.id}');
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(widget.user == null ? 'Novo usuário' : 'Editar usuário'),
    ),
    body: Form(
      key: _form,
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          TextFormField(
            controller: _username,
            decoration: const InputDecoration(labelText: 'Usuário'),
            autocorrect: false,
            validator: (v) => v?.trim().isEmpty != false
                ? 'Informe o usuário'
                : v!.length > 80
                ? 'Máximo 80 caracteres'
                : null,
          ),
          const SizedBox(height: 20),
          TextFormField(
            controller: _password,
            obscureText: true,
            decoration: InputDecoration(
              labelText: widget.user == null
                  ? 'Senha'
                  : 'Nova senha (opcional)',
            ),
            validator: (v) => widget.user == null && v?.isEmpty != false
                ? 'Informe a senha'
                : v?.isNotEmpty == true && v!.length < 6
                ? 'Mínimo 6 caracteres'
                : null,
          ),
          const SizedBox(height: 20),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Administrador'),
            value: _admin,
            onChanged: _self ? null : (v) => setState(() => _admin = v),
          ),
          if (widget.user != null)
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Usuário ativo'),
              value: _active,
              onChanged: _self ? null : (v) => setState(() => _active = v),
            ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Text(_busy ? 'Salvando…' : 'Salvar usuário'),
            ),
          ),
          if (widget.user != null && !_self && widget.user!.isActive) ...[
            const SizedBox(height: 20),
            OutlinedButton(
              onPressed: _busy ? null : _deactivate,
              child: const Text('Desativar usuário'),
            ),
          ],
        ],
      ),
    ),
  );
}
