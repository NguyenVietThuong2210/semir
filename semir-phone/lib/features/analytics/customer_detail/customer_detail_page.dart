import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/widgets/data_table_widget.dart';
import '../../../shared/widgets/error_banner.dart';
import '../../../shared/widgets/kpi_card.dart';
import '../../../shared/widgets/loading_overlay.dart';
import '../../../shared/widgets/section_header.dart';
import 'customer_detail_provider.dart';
import 'customer_detail_service.dart';

class CustomerDetailPage extends ConsumerStatefulWidget {
  const CustomerDetailPage({super.key});

  @override
  ConsumerState<CustomerDetailPage> createState() => _CustomerDetailPageState();
}

class _CustomerDetailPageState extends ConsumerState<CustomerDetailPage> {
  final _vipIdController = TextEditingController();
  final _phoneController = TextEditingController();

  @override
  void dispose() {
    _vipIdController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  void _search() {
    final vipId = _vipIdController.text.trim();
    final phone = _phoneController.text.trim();
    if (vipId.isEmpty && phone.isEmpty) return;
    ref.read(customerDetailProvider.notifier).search(
          vipId: vipId.isEmpty ? null : vipId,
          phone: phone.isEmpty ? null : phone,
        );
  }

  @override
  Widget build(BuildContext context) {
    final detailAsync = ref.watch(customerDetailProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Customer Lookup')),
      body: Stack(
        children: [
          ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // Search form
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      TextField(
                        controller: _vipIdController,
                        decoration: const InputDecoration(
                          labelText: 'VIP ID',
                          prefixIcon: Icon(Icons.badge_outlined),
                        ),
                        textInputAction: TextInputAction.next,
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _phoneController,
                        keyboardType: TextInputType.phone,
                        decoration: const InputDecoration(
                          labelText: 'Phone Number',
                          prefixIcon: Icon(Icons.phone_outlined),
                        ),
                        textInputAction: TextInputAction.search,
                        onSubmitted: (_) => _search(),
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton.icon(
                          icon: const Icon(Icons.search),
                          label: const Text('Search'),
                          onPressed: _search,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Results
              detailAsync.when(
                loading: () => const SizedBox.shrink(),
                error: (e, _) {
                  if (e is NotFoundException) {
                    return const _NotFoundBanner();
                  }
                  return ErrorBanner(
                    message: e.toString(),
                    onRetry: _search,
                  );
                },
                data: (payload) {
                  if (payload == null) return const SizedBox.shrink();
                  return _CustomerProfile(payload: payload);
                },
              ),
            ],
          ),
          if (detailAsync.isLoading) const LoadingOverlay(),
        ],
      ),
    );
  }
}

class _NotFoundBanner extends StatelessWidget {
  const _NotFoundBanner();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.grey.withAlpha(20),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.grey.withAlpha(60)),
      ),
      child: const Row(
        children: [
          Icon(Icons.person_off_outlined, color: Colors.grey),
          SizedBox(width: 12),
          Text('Customer not found'),
        ],
      ),
    );
  }
}

class _CustomerProfile extends StatelessWidget {
  const _CustomerProfile({required this.payload});
  final CustomerDetailPayload payload;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Profile card
        Card(
          child: Container(
            decoration: const BoxDecoration(
              border: Border(
                  top: BorderSide(color: AppColors.primary, width: 4)),
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(12),
                topRight: Radius.circular(12),
              ),
            ),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  payload.username,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 4),
                // Masked phone — never show full number
                Text(payload.phone,
                    style: const TextStyle(color: AppColors.textMuted)),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Text('VIP ID: ${payload.vipId}',
                        style:
                            const TextStyle(color: AppColors.textMuted)),
                    const SizedBox(width: 16),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withAlpha(20),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                            color: AppColors.primary.withAlpha(80)),
                      ),
                      child: Text(
                        payload.grade,
                        style: const TextStyle(
                            color: AppColors.primary, fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),

        // KPIs
        if (payload.kpis.isNotEmpty) ...[
          const SectionHeader(title: 'Statistics'),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: payload.kpis
                  .map((k) => SizedBox(
                        width: (MediaQuery.of(context).size.width - 48) / 2,
                        child: KpiCard(
                          label: k.label,
                          value: k.value,
                          variant: KpiVariant.period,
                        ),
                      ))
                  .toList(),
            ),
          ),
        ],

        // Invoice history
        if (payload.invoiceHeaders.isNotEmpty) ...[
          const SectionHeader(title: 'Invoice History'),
          SizedBox(
            height: 350,
            child: DataTableWidget(
              headers: payload.invoiceHeaders,
              rows: payload.invoiceRows,
            ),
          ),
        ],
      ],
    );
  }
}
