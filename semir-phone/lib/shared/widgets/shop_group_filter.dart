import 'package:flutter/material.dart';

class ShopGroupFilter extends StatelessWidget {
  const ShopGroupFilter({
    super.key,
    required this.onChanged,
    this.value,
  });

  final ValueChanged<String?> onChanged;
  final String? value;

  static const _groups = [
    'Bala Group',
    'Semir Group',
    'Others Group',
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Store Group',
          isDense: true,
          contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        ),
        child: DropdownButton<String>(
          value: (value == null || value == 'All') ? null : value,
          isExpanded: true,
          underline: const SizedBox.shrink(),
          items: [
            const DropdownMenuItem<String>(
              value: null,
              child: Text('All Stores'),
            ),
            ..._groups.map(
              (g) => DropdownMenuItem(value: g, child: Text(g)),
            ),
          ],
          onChanged: onChanged,
        ),
      ),
    );
  }
}
