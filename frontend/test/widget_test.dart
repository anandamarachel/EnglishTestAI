import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:english_day/app.dart';
import 'package:english_day/features/auth/presentation/splash_screen.dart';

void main() {
  testWidgets('EnglishDayApp smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(
      child: EnglishDayApp(home: SplashScreen(autoNavigate: false)),
    ));
    expect(find.text('English Day'), findsWidgets);
  });
}
