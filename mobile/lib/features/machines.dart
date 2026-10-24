import 'dart:async';
import 'package:flutter/material.dart';
import '../core/api_client.dart';
import '../models/models.dart';
import 'shared.dart';

class MachinesPage extends StatefulWidget {
  const MachinesPage({
    required this.api,
    this.initialFilters = const {},
    super.key,
  });
  final ApiClient api;
  final Map<String, String> initialFilters;
  @override
  State<MachinesPage> createState() => _MachinesPageState();
}

class _MachinesPageState extends State<MachinesPage> {
  final _content = GlobalKey<AsyncContentState<List<Json>>>();
  final _search = TextEditingController();
  late Map<String, String> _filters = {...widget.initialFilters};
  Timer? _debounce;
  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<void> _open(int id) async {
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => MachineDetailPage(api: widget.api, id: id),
      ),
    );
    _content.currentState?.refresh();
  }

  Future<void> _filter() async {
    final draft = {..._filters};
    final result = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) => SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Filtrar máquinas',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 20),
              for (final entry in filterOptions.entries)
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: DropdownButtonFormField<String>(
                    initialValue: draft[entry.key] ?? '',
                    decoration: InputDecoration(
                      labelText: filterLabels[entry.key],
                    ),
                    items: entry.value.entries
                        .map(
                          (e) => DropdownMenuItem(
                            value: e.key,
                            child: Text(e.value),
                          ),
                        )
                        .toList(),
                    onChanged: (value) => setModalState(() {
                      if (value == null || value.isEmpty) {
                        draft.remove(entry.key);
                      } else {
                        draft[entry.key] = value;
                      }
                    }),
                  ),
                ),
              Row(
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(context, <String, String>{}),
                    child: const Text('Limpar'),
                  ),
                  const Spacer(),
                  FilledButton(
                    onPressed: () => Navigator.pop(context, draft),
                    child: const Text('Aplicar filtros'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    if (result != null) {
      setState(() => _filters = result);
      _content.currentState?.refresh();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _search,
                  decoration: const InputDecoration(
                    hintText: 'Buscar nome, sala, IP…',
                    prefixIcon: Icon(Icons.search),
                  ),
                  onChanged: (_) {
                    _debounce?.cancel();
                    _debounce = Timer(
                      const Duration(milliseconds: 400),
                      () => _content.currentState?.refresh(),
                    );
                  },
                ),
              ),
              const SizedBox(width: 8),
              Badge(
                isLabelVisible: _filters.isNotEmpty,
                label: Text('${_filters.length}'),
                child: IconButton.filledTonal(
                  tooltip: 'Filtros',
                  onPressed: _filter,
                  icon: const Icon(Icons.tune),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: AsyncContent<List<Json>>(
            key: _content,
            load: () => widget.api.list(
              '/machines',
              query: {
                ..._filters,
                if (_search.text.trim().isNotEmpty) 'q': _search.text.trim(),
              },
            ),
            builder: (context, rows) => ListView(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 96),
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                if (rows.isEmpty)
                  const EmptyState(
                    'Nenhuma máquina encontrada para estes filtros.',
                  ),
                ...rows.map((row) {
                  final machine = Machine.fromJson(row);
                  return Card(
                    child: ListTile(
                      contentPadding: const EdgeInsets.all(14),
                      leading: CircleAvatar(child: Text(machine.profile)),
                      title: Text(
                        machine.name,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      subtitle: Text(
                        '${machine.room}\n${machine.data['ip'] ?? ''}',
                      ),
                      isThreeLine: true,
                      trailing: StatusBadge(machine.status),
                      onTap: () => _open(machine.id),
                    ),
                  );
                }),
              ],
            ),
          ),
        ),
      ],
    ),
    floatingActionButton: FloatingActionButton.extended(
      onPressed: () async {
        final saved = await Navigator.push<bool>(
          context,
          MaterialPageRoute(builder: (_) => MachineFormPage(api: widget.api)),
        );
        if (saved == true) _content.currentState?.refresh();
      },
      icon: const Icon(Icons.add),
      label: const Text('Máquina'),
    ),
  );
}

const filterLabels = {
  'profile': 'Perfil',
  'segment': 'Segmento',
  'room_status': 'Status da sala',
  'inspected': 'Vistoria',
  'checkup_done': 'Checkup',
};
const filterOptions = <String, Map<String, String>>{
  'profile': {
    '': 'Todos',
    'A': 'A · Infantil / Fundamental I',
    'B': 'B · Fundamental II / Médio',
    'C': 'C · Administrativo',
  },
  'segment': {
    '': 'Todos',
    'INFANTIL': 'Infantil',
    'FUND1': 'Fundamental I',
    'FUND2': 'Fundamental II',
    'EM': 'Ensino médio',
    'ADMIN': 'Administrativo',
    'OUTRO': 'Outros',
  },
  'room_status': {
    '': 'Todos',
    'OK': 'Tudo OK',
    'ATTENTION': 'Atenção',
    'URGENT': 'Urgente',
  },
  'inspected': {'': 'Todas', 'true': 'Realizada', 'false': 'Pendente'},
  'checkup_done': {'': 'Todos', 'true': 'Realizado', 'false': 'Pendente'},
};

class MachineDetailPage extends StatefulWidget {
  const MachineDetailPage({required this.api, required this.id, super.key});
  final ApiClient api;
  final int id;
  @override
  State<MachineDetailPage> createState() => _MachineDetailPageState();
}

class _MachineDetailPageState extends State<MachineDetailPage> {
  final _content = GlobalKey<AsyncContentState<Machine>>();
  bool _deleting = false;
  Future<void> _delete(Machine machine) async {
    if (!await confirm(
      context,
      'Excluir ${machine.name}?',
      'A máquina, seus chamados e heartbeats serão removidos do sistema. Esta ação não pode ser desfeita.',
    )) {
      return;
    }
    if (!mounted) return;
    setState(() => _deleting = true);
    try {
      await widget.api.request('DELETE', '/machines/${machine.id}');
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _deleting = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Detalhes da máquina')),
    body: AsyncContent<Machine>(
      key: _content,
      load: () => widget.api.machine(widget.id),
      builder: (context, machine) => ListView(
        padding: const EdgeInsets.all(20),
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  machine.name,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              StatusBadge(machine.status),
            ],
          ),
          const SizedBox(height: 8),
          Text(machine.room),
          const SizedBox(height: 20),
          FilledButton.tonalIcon(
            onPressed: () async {
              final saved = await Navigator.push<bool>(
                context,
                MaterialPageRoute(
                  builder: (_) =>
                      MachineFormPage(api: widget.api, machine: machine),
                ),
              );
              if (saved == true) _content.currentState?.refresh();
            },
            icon: const Icon(Icons.edit_outlined),
            label: const Text('Editar máquina'),
          ),
          const SectionTitle('Identificação e rede'),
          for (final key in [
            'profile',
            'ip',
            'mac_address',
            'username',
            'hoptodesk_id',
          ])
            InfoRow(machineLabels[key]!, machine.data[key]),
          const SectionTitle('Vistoria e checkup'),
          for (final key in [
            'inspected',
            'last_inspection_date',
            'checkup_done',
            'last_checkup_date',
          ])
            InfoRow(machineLabels[key]!, machine.data[key]),
          const SectionTitle('Hardware e software'),
          for (final key in [
            'os_name',
            'cpu_model',
            'ram_gb',
            'ram_modules',
            'gpu_type',
            'storage_type',
            'storage_gb',
            'office_installed',
            'office_version',
            'kaspersky_installed',
            'kaspersky_updated',
            'usb_ports_qty',
            'usb_ports_working',
            'adapters',
            'projector_lamp_hours',
          ])
            InfoRow(machineLabels[key]!, machine.data[key]),
          const SectionTitle('Periféricos'),
          ...machine.peripherals.map(
            (p) => Card(
              child: ListTile(
                leading: Icon(
                  flag(p['present'])
                      ? Icons.check_circle_outline
                      : Icons.remove_circle_outline,
                  color: flag(p['present']) ? Colors.green : Colors.grey,
                ),
                title: Text(
                  '${p['label'] ?? peripheralLabels[p['peripheral_code']] ?? p['peripheral_code']}',
                ),
                subtitle: Text(
                  !flag(p['present'])
                      ? 'Ausente'
                      : '${flag(p['tested_working']) ? 'Testado e funcionando' : 'Teste pendente'}${integer(p['quantity']) > 0 ? ' · ${p['quantity']} un.' : ''}',
                ),
              ),
            ),
          ),
          const SectionTitle('Manutenção'),
          SelectableText(
            '${machine.data['maintenance_description'] ?? 'Nenhuma observação.'}',
          ),
          const SectionTitle('Auditoria'),
          InfoRow('Criado por', machine.data['created_by']),
          InfoRow(
            'Criado em',
            displayDate(DateTime.tryParse('${machine.data['created_at']}')),
          ),
          InfoRow('Atualizado por', machine.data['updated_by']),
          InfoRow(
            'Atualizado em',
            displayDate(DateTime.tryParse('${machine.data['updated_at']}')),
          ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: _deleting ? null : () => _delete(machine),
            style: OutlinedButton.styleFrom(
              foregroundColor: Theme.of(context).colorScheme.error,
            ),
            icon: const Icon(Icons.delete_outline),
            label: Text(_deleting ? 'Excluindo…' : 'Excluir máquina'),
          ),
          const SizedBox(height: 24),
        ],
      ),
    ),
  );
}

const machineLabels = {
  'machine_name': 'Nome da máquina',
  'room_name': 'Sala',
  'ip': 'IP',
  'username': 'Usuário do PC',
  'profile': 'Perfil',
  'mac_address': 'MAC',
  'hoptodesk_id': 'HopToDesk ID',
  'inspected': 'Vistoria realizada',
  'last_inspection_date': 'Última vistoria',
  'checkup_done': 'Checkup realizado',
  'last_checkup_date': 'Último checkup',
  'os_name': 'Sistema operacional',
  'cpu_model': 'CPU',
  'ram_gb': 'RAM (GB)',
  'ram_modules': 'Módulos de RAM',
  'gpu_type': 'GPU',
  'storage_type': 'Armazenamento',
  'storage_gb': 'Capacidade (GB)',
  'office_installed': 'Office instalado',
  'office_version': 'Versão Office',
  'kaspersky_installed': 'Kaspersky instalado',
  'kaspersky_updated': 'Kaspersky atualizado',
  'usb_ports_qty': 'Portas USB',
  'usb_ports_working': 'USB funcionando',
  'adapters': 'Adaptadores',
  'projector_lamp_hours': 'Lâmpada (horas)',
  'maintenance_description': 'Manutenção / observações',
};
const integerFields = [
  'ram_gb',
  'ram_modules',
  'storage_gb',
  'usb_ports_qty',
  'projector_lamp_hours',
];
const booleanFields = [
  'office_installed',
  'kaspersky_installed',
  'kaspersky_updated',
  'usb_ports_working',
];
const requiredFields = ['machine_name', 'room_name', 'ip', 'username'];
const dateFields = ['last_inspection_date', 'last_checkup_date'];

class MachineFormPage extends StatefulWidget {
  const MachineFormPage({required this.api, this.machine, super.key});
  final ApiClient api;
  final Machine? machine;
  @override
  State<MachineFormPage> createState() => _MachineFormPageState();
}

class _MachineFormPageState extends State<MachineFormPage> {
  final _form = GlobalKey<FormState>();
  final Map<String, TextEditingController> _fields = {};
  final Map<String, bool?> _booleans = {};
  final Map<String, Json> _peripherals = {};
  late String _profile, _status;
  late bool _inspected, _checkup;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    final data = widget.machine?.data ?? <String, dynamic>{};
    for (final key in machineLabels.keys.where(
      (key) =>
          !booleanFields.contains(key) &&
          !['profile', 'inspected', 'checkup_done'].contains(key),
    )) {
      _fields[key] = TextEditingController(text: '${data[key] ?? ''}');
    }
    for (final key in booleanFields) {
      _booleans[key] = data[key] as bool?;
    }
    _profile = widget.machine?.profile ?? 'A';
    _status = widget.machine?.status ?? 'OK';
    _inspected = flag(data['inspected']);
    _checkup = flag(data['checkup_done']);
    for (final p in widget.machine?.peripherals ?? <Json>[]) {
      _peripherals['${p['peripheral_code']}'] = Map.from(p);
    }
  }

  @override
  void dispose() {
    for (final field in _fields.values) {
      field.dispose();
    }
    super.dispose();
  }

  Json _peripheral(String code) => _peripherals.putIfAbsent(
    code,
    () => {
      'peripheral_code': code,
      'present': false,
      'tested_working': false,
      'quantity': code == 'CABO_RCA' ? 2 : 0,
    },
  );
  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final data = <String, dynamic>{
        'profile': _profile,
        'room_status': _status,
        'inspected': _inspected,
        'checkup_done': _checkup,
        ..._booleans,
        for (final e in _fields.entries.where(
          (e) => e.key != 'projector_lamp_hours' || _profile == 'A',
        ))
          e.key: e.value.text.trim().isEmpty
              ? null
              : integerFields.contains(e.key)
              ? int.tryParse(e.value.text.trim())
              : e.value.text.trim(),
        'peripherals': peripheralCodes(_profile).map((code) {
          final p = _peripheral(code);
          return {
            'peripheral_code': code,
            'present': flag(p['present']),
            'tested_working': flag(p['present']) && flag(p['tested_working']),
            'quantity': code == 'CABO_RCA' && flag(p['present'])
                ? integer(p['quantity'])
                : 0,
          };
        }).toList(),
      };
      await widget.api.request(
        widget.machine == null ? 'POST' : 'PUT',
        '/machines${widget.machine == null ? '' : '/${widget.machine!.id}'}',
        body: data,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _field(String key) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: TextFormField(
      controller: _fields[key],
      maxLines: key == 'maintenance_description' || key == 'adapters' ? 3 : 1,
      decoration: InputDecoration(labelText: machineLabels[key]),
      keyboardType: integerFields.contains(key) ? TextInputType.number : null,
      validator: (value) {
        if (requiredFields.contains(key) && value?.trim().isEmpty != false) {
          return 'Campo obrigatório';
        }
        if (integerFields.contains(key) &&
            value?.isNotEmpty == true &&
            (int.tryParse(value!) == null || int.parse(value) < 0)) {
          return 'Informe inteiro maior ou igual a zero';
        }
        if ((value?.length ?? 0) >
            (['maintenance_description', 'adapters'].contains(key)
                ? 10000
                : key == 'mac_address'
                ? 32
                : key == 'hoptodesk_id'
                ? 64
                : key == 'ip'
                ? 64
                : key == 'office_version'
                ? 60
                : 120)) {
          return 'Texto muito longo';
        }
        return null;
      },
    ),
  );
  Future<void> _pickDate(String key) async {
    final now = DateTime.now();
    final minimum = DateTime(2000);
    final stored = DateTime.tryParse(_fields[key]!.text) ?? now;
    final initial = stored.isBefore(minimum)
        ? minimum
        : stored.isAfter(now)
        ? now
        : stored;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: minimum,
      lastDate: now,
    );
    if (picked != null) {
      setState(
        () => _fields[key]!.text = picked.toIso8601String().substring(0, 10),
      );
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.machine == null ? 'Cadastrar máquina' : 'Editar máquina',
      ),
    ),
    body: Form(
      key: _form,
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const SectionTitle('Identificação'),
          for (final key in requiredFields) _field(key),
          DropdownButtonFormField<String>(
            initialValue: _profile,
            decoration: const InputDecoration(labelText: 'Perfil'),
            items: filterOptions['profile']!.entries
                .where((e) => e.key.isNotEmpty)
                .map(
                  (e) => DropdownMenuItem(value: e.key, child: Text(e.value)),
                )
                .toList(),
            onChanged: (value) => setState(() => _profile = value!),
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            initialValue: _status,
            decoration: const InputDecoration(labelText: 'Status da sala'),
            items: ['OK', 'ATTENTION', 'URGENT']
                .map(
                  (s) =>
                      DropdownMenuItem(value: s, child: Text(statusLabels[s]!)),
                )
                .toList(),
            onChanged: (value) => _status = value!,
          ),
          const SectionTitle('Rede e acesso remoto'),
          _field('mac_address'),
          _field('hoptodesk_id'),
          const SectionTitle('Vistoria e checkup'),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Vistoria realizada'),
            value: _inspected,
            onChanged: (v) => setState(() {
              _inspected = v;
              if (v && _fields['last_inspection_date']!.text.isEmpty) {
                _fields['last_inspection_date']!.text = DateTime.now()
                    .toIso8601String()
                    .substring(0, 10);
              }
            }),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Checkup realizado'),
            value: _checkup,
            onChanged: (v) => setState(() {
              _checkup = v;
              if (v && _fields['last_checkup_date']!.text.isEmpty) {
                _fields['last_checkup_date']!.text = DateTime.now()
                    .toIso8601String()
                    .substring(0, 10);
              }
            }),
          ),
          for (final key in dateFields)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _fields[key],
                readOnly: true,
                decoration: InputDecoration(
                  labelText: machineLabels[key],
                  suffixIcon: IconButton(
                    tooltip: 'Limpar data',
                    icon: const Icon(Icons.clear),
                    onPressed: () => _fields[key]!.clear(),
                  ),
                ),
                onTap: () => _pickDate(key),
              ),
            ),
          const SectionTitle('Hardware e software'),
          for (final key in [
            'os_name',
            'cpu_model',
            'ram_gb',
            'ram_modules',
            'gpu_type',
            'storage_type',
            'storage_gb',
            'office_version',
            'usb_ports_qty',
            'adapters',
            if (_profile == 'A') 'projector_lamp_hours',
          ])
            _field(key),
          for (final key in booleanFields)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: DropdownButtonFormField<String>(
                initialValue: _booleans[key]?.toString() ?? '',
                decoration: InputDecoration(labelText: machineLabels[key]),
                items: const [
                  DropdownMenuItem(value: '', child: Text('Não informado')),
                  DropdownMenuItem(value: 'true', child: Text('Sim')),
                  DropdownMenuItem(value: 'false', child: Text('Não')),
                ],
                onChanged: (value) =>
                    _booleans[key] = value == '' ? null : value == 'true',
              ),
            ),
          const SectionTitle('Periféricos'),
          ...peripheralCodes(_profile).map((code) {
            final p = _peripheral(code);
            return Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(peripheralLabels[code]!),
                      subtitle: const Text('Presente'),
                      value: flag(p['present']),
                      onChanged: (v) => setState(() {
                        p['present'] = v;
                        if (!v) p['tested_working'] = false;
                      }),
                    ),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Testado e funcionando'),
                      value: flag(p['tested_working']),
                      onChanged: flag(p['present'])
                          ? (v) => setState(() => p['tested_working'] = v)
                          : null,
                    ),
                    if (code == 'CABO_RCA')
                      TextFormField(
                        key: ValueKey('qty-$_profile'),
                        initialValue: '${p['quantity']}',
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Quantidade',
                        ),
                        validator: (v) =>
                            flag(p['present']) &&
                                ((int.tryParse(v ?? '') ?? 0) < 1)
                            ? 'Informe quantidade maior que zero'
                            : null,
                        onChanged: (v) => p['quantity'] = int.tryParse(v) ?? 0,
                      ),
                  ],
                ),
              ),
            );
          }),
          const SectionTitle('Observações'),
          _field('maintenance_description'),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _busy ? null : _save,
            icon: const Icon(Icons.save_outlined),
            label: Padding(
              padding: const EdgeInsets.all(14),
              child: Text(_busy ? 'Salvando…' : 'Salvar máquina'),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    ),
  );
}
