import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

class AppPanelSkeleton extends StatefulWidget {
  const AppPanelSkeleton({
    super.key,
    this.cards = 4,
    this.compact = false,
    this.padding = AppSpacing.screenPadding,
  });

  final int cards;
  final bool compact;
  final EdgeInsetsGeometry padding;

  @override
  State<AppPanelSkeleton> createState() => _AppPanelSkeletonState();
}

class _AppPanelSkeletonState extends State<AppPanelSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(begin: 0.45, end: 0.9).animate(_controller),
      child: ListView.separated(
        physics: const NeverScrollableScrollPhysics(),
        padding: widget.padding,
        itemCount: widget.cards,
        separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.md),
        itemBuilder: (_, index) => _SkeletonCard(
          compact: widget.compact,
          featured: !widget.compact && index == 0,
        ),
      ),
    );
  }
}

class AppSheetSkeleton extends StatelessWidget {
  const AppSheetSkeleton({super.key, this.rows = 3});

  final int rows;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: rows * 64,
      child: AppPanelSkeleton(
        cards: rows,
        compact: true,
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      ),
    );
  }
}

class _SkeletonCard extends StatelessWidget {
  const _SkeletonCard({required this.compact, required this.featured});

  final bool compact;
  final bool featured;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: EdgeInsets.all(compact ? AppSpacing.md : AppSpacing.df),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: compact ? 36 : 44,
            height: compact ? 36 : 44,
            decoration: BoxDecoration(
              color: AppColors.fieldBackground,
              borderRadius: AppSpacing.borderRadiusMd,
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                FractionallySizedBox(
                  widthFactor: featured ? 0.72 : 0.58,
                  child: const _SkeletonBar(height: 14),
                ),
                const SizedBox(height: AppSpacing.sm),
                const FractionallySizedBox(
                  widthFactor: 0.42,
                  child: _SkeletonBar(height: 11),
                ),
                if (!compact) ...[
                  const SizedBox(height: AppSpacing.md),
                  const FractionallySizedBox(
                    widthFactor: 0.88,
                    child: _SkeletonBar(height: 11),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SkeletonBar extends StatelessWidget {
  const _SkeletonBar({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: AppColors.lightGrey,
        borderRadius: BorderRadius.circular(999),
      ),
    );
  }
}
