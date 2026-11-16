import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/dev/gallery_screen.dart';

/// Renders every screen/state from the design gallery. Catches screens that throw
/// while building (broken imports, missing data, null errors) after refactors.
///
/// Layout overflows are reported but not failed: tests cannot download the Google
/// Fonts, so text uses Flutter's test font, whose square glyphs are much wider than
/// Plus Jakarta Sans. Check overflows on a real device or emulator instead.
void main() {
  test('gallery lists every design state', () {
    final total = GalleryScreen.entries.values.fold<int>(0, (n, list) => n + list.length);
    expect(total, 58);
  });

  for (final group in GalleryScreen.entries.entries) {
    for (final (name, builder) in group.value) {
      testWidgets('${group.key} · $name renders', (tester) async {
        tester.view.physicalSize = const Size(1080, 2400); // phone-sized portrait
        tester.view.devicePixelRatio = 3;
        addTearDown(tester.view.reset);

        final reportError = FlutterError.onError!;
        FlutterError.onError = (details) {
          if (details.exceptionAsString().contains('overflowed')) {
            debugPrint('overflow (test font): ${group.key} · $name');
          } else {
            reportError(details);
          }
        };

        await tester.pumpWidget(ProviderScope(
          child: MaterialApp(theme: AppTheme.light, home: Builder(builder: builder)),
        ));
        await tester.pump(const Duration(milliseconds: 500));

        // Unmount, then let any simulated delays (dummy "AI" timers) run out.
        await tester.pumpWidget(const SizedBox());
        await tester.pump(const Duration(seconds: 15));
        FlutterError.onError = reportError;
      });
    }
  }
}
