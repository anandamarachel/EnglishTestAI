import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_web_plugins/url_strategy.dart';

import 'package:english_day_admin/app.dart';

void main() {
  usePathUrlStrategy(); // /students/s001 instead of /#/students/s001
  runApp(const ProviderScope(child: AdminApp()));
}
