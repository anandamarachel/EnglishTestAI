import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';

/// Latar kertas bergaris.
class _LinesPainter extends CustomPainter {
  _LinesPainter({required this.lineHeight, required this.top});
  final double lineHeight;
  final double top;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.divider
      ..strokeWidth = 1;
    for (var y = top + lineHeight; y < size.height - 4; y += lineHeight) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _LinesPainter old) =>
      old.lineHeight != lineHeight || old.top != top;
}

class LinedPaper extends StatelessWidget {
  const LinedPaper({
    super.key,
    required this.child,
    this.lineHeight = 28,
    this.minLines = 5,
    this.height,
  });

  final Widget child;
  final double lineHeight;
  final int minLines;
  final double? height;

  static const _padTop = 16.0;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      constraints: BoxConstraints(minHeight: _padTop * 2 + lineHeight * minLines),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      padding: const EdgeInsets.fromLTRB(16, _padTop, 16, _padTop),
      child: CustomPaint(
        painter: _LinesPainter(lineHeight: lineHeight, top: 0),
        child: child,
      ),
    );
  }
}

/// Teks serif di atas kertas bergaris.
class LinedText extends StatelessWidget {
  const LinedText(this.text, {super.key, this.minLines = 5});
  final String text;
  final int minLines;

  @override
  Widget build(BuildContext context) {
    return LinedPaper(
      minLines: minLines,
      child: SizedBox(
        width: double.infinity,
        child: Text(text,
            style: AppText.serif(size: 18, color: AppColors.primary, height: 28 / 18)),
      ),
    );
  }
}

/// Satu token teks pada hasil koreksi.
class CorrectionToken {
  const CorrectionToken(this.text, {this.correction, this.ruleId, this.trailingSpace = true});
  final String text;
  final String? correction;
  final String? ruleId;

  /// False when the next token follows without a space (e.g. "friends" + ",").
  final bool trailingSpace;
  bool get isWrong => correction != null;
}

/// Teks dengan kata yang dicoret merah + koreksi di atasnya.
class CorrectionText extends StatelessWidget {
  const CorrectionText({super.key, required this.tokens, this.onTapCorrection});
  final List<CorrectionToken> tokens;
  final ValueChanged<CorrectionToken>? onTapCorrection;

  static const _line = 56.0;

  @override
  Widget build(BuildContext context) {
    final style = AppText.serif(size: 18, color: AppColors.primary);
    return LinedPaper(
      lineHeight: _line,
      minLines: 3,
      child: SizedBox(
        width: double.infinity,
        child: Wrap(
          children: [
            for (final t in tokens)
              SizedBox(
                height: _line,
                child: t.isWrong
                    ? GestureDetector(
                        onTap: () => onTapCorrection?.call(t),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            // Tight line height + Flexible: the correction must fit in
                            // the fixed _line height above the struck word (Source Serif
                            // line boxes are taller than the glyphs) and may shrink
                            // instead of overflowing when the system text size grows.
                            Flexible(
                              child: Text(t.correction!,
                                  style: AppText.serif(
                                      size: 14,
                                      color: AppColors.primary,
                                      style: FontStyle.italic,
                                      height: 1.0)),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${t.text}${t.trailingSpace ? ' ' : ''}',
                              style: style.copyWith(
                                decoration: TextDecoration.lineThrough,
                                decorationColor: AppColors.error,
                                decorationThickness: 2,
                                color: AppColors.primary,
                              ),
                            ),
                            const SizedBox(height: 8),
                          ],
                        ),
                      )
                    : Column(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Text('${t.text}${t.trailingSpace ? ' ' : ''}', style: style),
                          const SizedBox(height: 8),
                        ],
                      ),
              ),
          ],
        ),
      ),
    );
  }
}
