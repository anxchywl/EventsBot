import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_text_styles.dart';

/// Circular level/XP ring indicator.
/// Used for gamification features to show user level progress.
/// 
/// Example:
/// ```dart
/// AppLevelRing(
///   level: 5,
///   progress: 0.65,
///   size: 100,
/// )
/// ```
class AppLevelRing extends StatelessWidget {
  const AppLevelRing({
    super.key,
    required this.level,
    required this.progress,
    this.size = 80,
    this.strokeWidth = 6,
    this.backgroundColor,
    this.progressColor,
    this.showLevel = true,
    this.centerWidget,
    this.avatarUrl,
  });

  /// Current level number.
  final int level;

  /// Progress to next level (0.0 to 1.0).
  final double progress;

  /// Size of the ring.
  final double size;

  /// Stroke width of the ring.
  final double strokeWidth;

  /// Background color of the ring.
  final Color? backgroundColor;

  /// Progress color of the ring.
  final Color? progressColor;

  /// Whether to show level number in center.
  final bool showLevel;

  /// Custom center widget (takes precedence over level display).
  final Widget? centerWidget;

  /// Avatar URL to show in center.
  final String? avatarUrl;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    
    final effectiveBackgroundColor = backgroundColor 
        ?? (isLight ? AppColors.fieldBackground : AppColors.surfaceDark);
    final effectiveProgressColor = progressColor ?? _getLevelColor(level);
    final clampedProgress = progress.clamp(0.0, 1.0);

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Background ring
          CustomPaint(
            size: Size(size, size),
            painter: _RingPainter(
              progress: 1.0,
              color: effectiveBackgroundColor,
              strokeWidth: strokeWidth,
            ),
          ),
          // Progress ring
          CustomPaint(
            size: Size(size, size),
            painter: _RingPainter(
              progress: clampedProgress,
              color: effectiveProgressColor,
              strokeWidth: strokeWidth,
            ),
          ),
          // Center content
          _buildCenterContent(isLight, effectiveProgressColor),
        ],
      ),
    );
  }

  Widget _buildCenterContent(bool isLight, Color progressColor) {
    if (centerWidget != null) {
      return centerWidget!;
    }

    if (avatarUrl != null) {
      return Container(
        width: size - strokeWidth * 2 - 4,
        height: size - strokeWidth * 2 - 4,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          image: DecorationImage(
            image: NetworkImage(avatarUrl!),
            fit: BoxFit.cover,
          ),
        ),
      );
    }

    if (showLevel) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '$level',
            style: AppTextStyles.headlineMedium.copyWith(
              color: progressColor,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            'LVL',
            style: AppTextStyles.labelSmall.copyWith(
              color: AppColors.grey,
            ),
          ),
        ],
      );
    }

    return const SizedBox.shrink();
  }

  Color _getLevelColor(int level) {
    if (level < 5) return AppColors.success;
    if (level < 10) return AppColors.blue;
    if (level < 20) return AppColors.purple;
    if (level < 50) return AppColors.gold;
    return AppColors.primary;
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({
    required this.progress,
    required this.color,
    required this.strokeWidth,
  });

  final double progress;
  final Color color;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - strokeWidth) / 2;

    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    final sweepAngle = 2 * math.pi * progress;
    const startAngle = -math.pi / 2; // Start from top

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepAngle,
      false,
      paint,
    );
  }

  @override
  bool shouldRepaint(_RingPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.color != color ||
        oldDelegate.strokeWidth != strokeWidth;
  }
}

/// Simple circular progress with text.
class AppCircularProgress extends StatelessWidget {
  const AppCircularProgress({
    super.key,
    required this.progress,
    this.size = 60,
    this.strokeWidth = 4,
    this.backgroundColor,
    this.progressColor,
    this.showPercentage = true,
    this.centerWidget,
  });

  /// Progress value (0.0 to 1.0).
  final double progress;

  /// Size of the indicator.
  final double size;

  /// Stroke width.
  final double strokeWidth;

  /// Background color.
  final Color? backgroundColor;

  /// Progress color.
  final Color? progressColor;

  /// Whether to show percentage in center.
  final bool showPercentage;

  /// Custom center widget.
  final Widget? centerWidget;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    
    final effectiveBackgroundColor = backgroundColor 
        ?? (isLight ? AppColors.fieldBackground : AppColors.surfaceDark);
    final effectiveProgressColor = progressColor ?? AppColors.primary;
    final clampedProgress = progress.clamp(0.0, 1.0);

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          CustomPaint(
            size: Size(size, size),
            painter: _RingPainter(
              progress: 1.0,
              color: effectiveBackgroundColor,
              strokeWidth: strokeWidth,
            ),
          ),
          CustomPaint(
            size: Size(size, size),
            painter: _RingPainter(
              progress: clampedProgress,
              color: effectiveProgressColor,
              strokeWidth: strokeWidth,
            ),
          ),
          if (centerWidget != null)
            centerWidget!
          else if (showPercentage)
            Text(
              '${(clampedProgress * 100).toInt()}%',
              style: AppTextStyles.labelMedium.copyWith(
                color: isLight ? AppColors.textPrimary : AppColors.textPrimaryDark,
                fontWeight: FontWeight.w600,
              ),
            ),
        ],
      ),
    );
  }
}
