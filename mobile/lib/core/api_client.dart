import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class ApiException implements Exception {
  const ApiException(this.message, [this.status]);
  final String message;
  final int? status;
  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client, this.timeout = const Duration(seconds: 15)})
    : _client = client ?? http.Client();
  final http.Client _client;
  final Duration timeout;
  String baseUrl = '';
  String? token;
  void Function()? onUnauthorized;

  static String normalizeBaseUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw const ApiException(
        'Informe endereço completo, como http://192.168.1.10:8000, sem caminho ou credenciais.',
      );
    }
    return uri.replace(path: '').toString().replaceFirst(RegExp(r'/$'), '');
  }

  Future<dynamic> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool auth = true,
  }) async {
    if (baseUrl.isEmpty) {
      throw const ApiException('Configure o servidor para continuar.');
    }
    final activeToken = token;
    final uri = Uri.parse(
      '$baseUrl/api/v1$path',
    ).replace(queryParameters: query);
    final request = http.Request(method, uri)
      ..headers['Accept'] = 'application/json';
    if (auth && activeToken != null) {
      request.headers['Authorization'] = 'Bearer $activeToken';
    }
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final response = await (() async {
        return http.Response.fromStream(await _client.send(request));
      })().timeout(timeout);
      dynamic data;
      try {
        data = response.body.isEmpty
            ? null
            : jsonDecode(utf8.decode(response.bodyBytes));
      } on FormatException {
        throw const ApiException(
          'Resposta inválida do servidor. Verifique a URL e a versão da API.',
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        if (response.statusCode == 401 && auth && token == activeToken) {
          onUnauthorized?.call();
        }
        final detail = object(data)['detail'];
        final message = detail is String
            ? detail
            : detail is List
            ? detail
                  .map((e) => '${object(e)['loc']}: ${object(e)['msg']}')
                  .join('\n')
            : 'Falha ao executar operação (HTTP ${response.statusCode}).';
        throw ApiException(message, response.statusCode);
      }
      return data;
    } on TimeoutException {
      throw const ApiException(
        'Servidor demorou a responder. Tente novamente.',
      );
    } on HandshakeException {
      throw const ApiException(
        'Certificado HTTPS não confiável. Configure certificado válido no servidor e no dispositivo.',
      );
    } on SocketException {
      throw const ApiException(
        'Servidor indisponível. Verifique Wi-Fi e endereço configurado.',
      );
    } on http.ClientException {
      throw const ApiException(
        'Conexão interrompida. Verifique sua rede e tente novamente.',
      );
    }
  }

  Future<List<Json>> list(String path, {Map<String, String>? query}) async {
    final data = await request('GET', path, query: query);
    if (data is List) return data.map(object).toList();
    final values = object(data);
    final items = values['items'] ?? values[path.substring(1)];
    if (items is List) return items.map(object).toList();
    throw const ApiException('Lista inválida retornada pelo servidor.');
  }

  Future<Ticket> ticket(int id) async =>
      Ticket.fromJson(object(await request('GET', '/tickets/$id')));
  Future<Machine> machine(int id) async =>
      Machine.fromJson(object(await request('GET', '/machines/$id')));
  void dispose() => _client.close();
}
