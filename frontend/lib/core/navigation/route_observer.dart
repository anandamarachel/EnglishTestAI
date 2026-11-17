import 'package:flutter/widgets.dart';

/// Lets a screen know when it is visible again after the screens above it closed
/// (`RouteAware.didPopNext`), however they were closed or replaced.
final appRouteObserver = RouteObserver<ModalRoute<void>>();
