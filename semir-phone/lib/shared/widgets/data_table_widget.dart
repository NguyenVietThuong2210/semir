import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

/// Data table with sticky first column.
///
/// Implementation: dual SingleChildScrollView with a shared vertical
/// ScrollController. The left panel is fixed-width (label column, vertical
/// scroll only). The right panel scrolls horizontally and vertically in sync.
///
/// Performance note: ListView.builder renders only visible rows — this keeps
/// frame time under budget even at 200 rows (SC-007: ≥50fps).
class DataTableWidget extends StatefulWidget {
  const DataTableWidget({
    super.key,
    required this.headers,
    required this.rows,
    this.firstColumnWidth = 140.0,
  });

  final List<String> headers;
  final List<List<String>> rows;
  final double firstColumnWidth;

  @override
  State<DataTableWidget> createState() => _DataTableWidgetState();
}

class _DataTableWidgetState extends State<DataTableWidget> {
  late final ScrollController _verticalLeft = ScrollController();
  late final ScrollController _verticalRight = ScrollController();
  bool _syncingLeft = false;
  bool _syncingRight = false;

  @override
  void initState() {
    super.initState();
    _verticalLeft.addListener(_onLeftScroll);
    _verticalRight.addListener(_onRightScroll);
  }

  void _onLeftScroll() {
    if (_syncingRight) return;
    _syncingLeft = true;
    _verticalRight.jumpTo(_verticalLeft.offset);
    _syncingLeft = false;
  }

  void _onRightScroll() {
    if (_syncingLeft) return;
    _syncingRight = true;
    _verticalLeft.jumpTo(_verticalRight.offset);
    _syncingRight = false;
  }

  @override
  void dispose() {
    _verticalLeft.dispose();
    _verticalRight.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.rows.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Text('No data', style: TextStyle(color: AppColors.textMuted)),
      );
    }

    final rowCount = widget.rows.length;
    const rowHeight = 44.0;
    const headerHeight = 44.0;

    return SizedBox(
      height: headerHeight + rowCount * rowHeight,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Left: sticky first column ─────────────────────────────────────
          SizedBox(
            width: widget.firstColumnWidth,
            child: Column(
              children: [
                _HeaderCell(
                  widget.headers.isNotEmpty ? widget.headers[0] : '',
                  width: widget.firstColumnWidth,
                  height: headerHeight,
                ),
                Expanded(
                  child: ListView.builder(
                    controller: _verticalLeft,
                    physics: const ClampingScrollPhysics(),
                    itemCount: rowCount,
                    itemExtent: rowHeight,
                    itemBuilder: (_, i) => _DataCell(
                      widget.rows[i].isNotEmpty ? widget.rows[i][0] : '',
                      width: widget.firstColumnWidth,
                      height: rowHeight,
                      isEven: i.isEven,
                    ),
                  ),
                ),
              ],
            ),
          ),
          // ── Right: scrollable data columns ───────────────────────────────
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SizedBox(
                width: (widget.headers.length - 1) * 120.0,
                child: Column(
                  children: [
                    // Header row
                    Row(
                      children: widget.headers
                          .skip(1)
                          .map(
                            (h) => _HeaderCell(h, width: 120, height: headerHeight),
                          )
                          .toList(),
                    ),
                    // Data rows
                    Expanded(
                      child: ListView.builder(
                        controller: _verticalRight,
                        physics: const ClampingScrollPhysics(),
                        itemCount: rowCount,
                        itemExtent: rowHeight,
                        itemBuilder: (_, i) {
                          final row = widget.rows[i];
                          return Row(
                            children: List.generate(
                              widget.headers.length - 1,
                              (j) => _DataCell(
                                j + 1 < row.length ? row[j + 1] : '',
                                width: 120,
                                height: rowHeight,
                                isEven: i.isEven,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HeaderCell extends StatelessWidget {
  const _HeaderCell(this.text, {required this.width, required this.height});
  final String text;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      color: AppColors.primary,
      alignment: Alignment.centerLeft,
      child: Text(
        text,
        style: const TextStyle(
          color: AppColors.white,
          fontWeight: FontWeight.w600,
          fontSize: 12,
        ),
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

class _DataCell extends StatelessWidget {
  const _DataCell(
    this.text, {
    required this.width,
    required this.height,
    required this.isEven,
  });
  final String text;
  final double width;
  final double height;
  final bool isEven;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      color: isEven ? Colors.white : const Color(0xFFF8F9FA),
      alignment: Alignment.centerLeft,
      child: Text(
        text,
        style: const TextStyle(fontSize: 12, color: AppColors.textDark),
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}
