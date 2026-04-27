/// Shared analytics value types used across all analytics feature services.
library;

class PermissionException implements Exception {
  const PermissionException();
}

class ParseException implements Exception {
  const ParseException(this.message);
  final String message;
}

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class KpiItem {
  const KpiItem({required this.label, required this.value});
  final String label;
  final String value;

  static List<KpiItem> parseMap(Map<String, dynamic>? map) {
    if (map == null) return [];
    return map.entries
        .map((e) => KpiItem(label: e.key, value: '${e.value}'))
        .toList();
  }
}

class TableTab {
  const TableTab({
    required this.tabKey,
    required this.label,
    required this.headers,
    required this.rows,
  });
  final String tabKey;
  final String label;
  final List<String> headers;
  final List<List<String>> rows;

  static List<TableTab> parseMap(Map<String, dynamic>? tabs) {
    if (tabs == null) return [];
    return tabs.entries.map((e) {
      final d = e.value as Map<String, dynamic>;
      return TableTab(
        tabKey: e.key,
        label: d['label'] as String? ?? e.key,
        headers: (d['headers'] as List?)?.cast<String>() ?? [],
        rows: (d['rows'] as List?)
                ?.map((r) => (r as List).cast<String>())
                .toList() ??
            [],
      );
    }).toList();
  }
}
