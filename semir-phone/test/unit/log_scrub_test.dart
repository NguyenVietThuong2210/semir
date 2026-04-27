import 'package:flutter_test/flutter_test.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

// Import the PII scrubber function from main.dart
// We test it in isolation here to verify SC-008.
import 'package:semir_phone/main.dart' show scrubPiiForTest;

void main() {
  group('Sentry beforeSend PII scrubber (SC-008)', () {
    SentryEvent _makeEvent(Map<String, dynamic> extra) {
      return SentryEvent(extra: extra);
    }

    test('phone field is redacted', () {
      final event = _makeEvent({'phone': '0912345678', 'other': 'data'});
      final hint = Hint();
      final scrubbed = scrubPiiForTest(event, hint);
      expect(scrubbed?.extra?['phone'], '[REDACTED]');
      expect(scrubbed?.extra?['other'], 'data');
    });

    test('vip_id field is redacted', () {
      final event = _makeEvent({'vip_id': 'VIP12345'});
      final scrubbed = scrubPiiForTest(event, Hint());
      expect(scrubbed?.extra?['vip_id'], '[REDACTED]');
    });

    test('invoice field is redacted', () {
      final event = _makeEvent({'invoice': 'INV-001234'});
      final scrubbed = scrubPiiForTest(event, Hint());
      expect(scrubbed?.extra?['invoice'], '[REDACTED]');
    });

    test('token field is redacted', () {
      final event = _makeEvent({'token': 'eyJhbGciOiJIUzI1NiJ9'});
      final scrubbed = scrubPiiForTest(event, Hint());
      expect(scrubbed?.extra?['token'], '[REDACTED]');
    });

    test('password field is redacted', () {
      final event = _makeEvent({'password': 'secret123'});
      final scrubbed = scrubPiiForTest(event, Hint());
      expect(scrubbed?.extra?['password'], '[REDACTED]');
    });

    test('non-sensitive fields pass through unchanged', () {
      final event = _makeEvent({
        'page': 'sales_analytics',
        'filter': 'last_30_days',
        'tab': 'by_season',
      });
      final scrubbed = scrubPiiForTest(event, Hint());
      expect(scrubbed?.extra?['page'], 'sales_analytics');
      expect(scrubbed?.extra?['filter'], 'last_30_days');
      expect(scrubbed?.extra?['tab'], 'by_season');
    });

    test('nested phone field is redacted', () {
      final event = _makeEvent({
        'context': {'phone': '0912345678', 'name': 'Test User'},
      });
      final scrubbed = scrubPiiForTest(event, Hint());
      final ctx = scrubbed?.extra?['context'] as Map<String, dynamic>?;
      expect(ctx?['phone'], '[REDACTED]');
      expect(ctx?['name'], 'Test User');
    });

    test('event with no extra returns unchanged', () {
      final event = SentryEvent();
      final scrubbed = scrubPiiForTest(event, Hint());
      expect(scrubbed?.extra, isNull);
    });
  });
}
