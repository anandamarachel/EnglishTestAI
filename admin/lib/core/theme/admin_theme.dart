import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Design tokens from the English Day Admin style sheet (Stitch reference).
class AdminColors {
  AdminColors._();

  static const primary = Color(0xFF1D4ED8);
  static const primaryDark = Color(0xFF1E40AF);
  static const secondary = Color(0xFF3B82F6);
  static const tertiary = Color(0xFF1E3A8A);
  static const neutral = Color(0xFF64748B);

  static const primarySoft = Color(0xFFE8EFFE); // chips, selected nav, badges
  static const primaryTint = Color(0xFFF1F5FF); // subtle row/panel fill
  static const background = Color(0xFFF5F8FF);
  static const surface = Colors.white;
  static const border = Color(0xFFE2E8F0);
  static const divider = Color(0xFFEDF1F7);

  static const textPrimary = Color(0xFF0F172A);
  static const textSecondary = Color(0xFF64748B);
  static const textMuted = Color(0xFF94A3B8);

  static const success = Color(0xFF16A34A);
  static const successSoft = Color(0xFFE7F7EE);
  static const warning = Color(0xFFD97706);
  static const warningSoft = Color(0xFFFEF3E2);
  static const danger = Color(0xFFB91C1C);
  static const dangerSoft = Color(0xFFFDECEC);

  /// Skill accents (bars and badges).
  static const writing = Color(0xFF1D4ED8);
  static const reading = Color(0xFF1E3A8A);
  static const speaking = Color(0xFF3B82F6);
  static const listening = Color(0xFF64748B);
}

/// Headlines: Plus Jakarta Sans. Body and labels: Inter.
class AdminText {
  AdminText._();

  static TextStyle headline({
    double size = 28,
    FontWeight weight = FontWeight.w800,
    Color color = AdminColors.textPrimary,
    double? height,
  }) =>
      GoogleFonts.plusJakartaSans(
          fontSize: size, fontWeight: weight, color: color, height: height);

  static TextStyle body({
    double size = 14,
    FontWeight weight = FontWeight.w400,
    Color color = AdminColors.textPrimary,
    double? height,
    double? letterSpacing,
  }) =>
      GoogleFonts.inter(
        fontSize: size,
        fontWeight: weight,
        color: color,
        height: height,
        letterSpacing: letterSpacing,
      );

  static TextStyle get pageTitle => headline(size: 28);
  static TextStyle get sectionTitle => headline(size: 17, weight: FontWeight.w700);
  static TextStyle get statValue => headline(size: 30, weight: FontWeight.w800);
  static TextStyle get small => body(size: 12.5, color: AdminColors.textSecondary);

  /// Upper-case table headers and card captions.
  static TextStyle get caps => body(
      size: 11, weight: FontWeight.w700, color: AdminColors.textSecondary, letterSpacing: 0.6);
}

class AdminTheme {
  AdminTheme._();

  static ThemeData get light {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AdminColors.primary,
        primary: AdminColors.primary,
        secondary: AdminColors.secondary,
        tertiary: AdminColors.tertiary,
        surface: AdminColors.surface,
      ),
      scaffoldBackgroundColor: AdminColors.background,
    );
    return base.copyWith(
      textTheme: GoogleFonts.interTextTheme(base.textTheme),
      dividerColor: AdminColors.divider,
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AdminColors.primaryTint,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        hintStyle: AdminText.body(color: AdminColors.textMuted),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AdminColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AdminColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AdminColors.primary, width: 1.4),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AdminColors.danger),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AdminColors.primary,
          foregroundColor: Colors.white,
          minimumSize: const Size(0, 46),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          textStyle: AdminText.body(weight: FontWeight.w600),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AdminColors.primary,
          textStyle: AdminText.body(weight: FontWeight.w600, size: 13),
        ),
      ),
    );
  }
}
