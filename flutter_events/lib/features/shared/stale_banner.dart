import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/localization.dart';

/// Non-intrusive hint shown when a screen is serving cached data because a
/// background refresh could not complete and the data has aged past
/// [CacheTtl.stalenessThreshold]. Deliberately quiet: a thin strip, never a
/// blocking error.
class StaleBanner extends StatelessWidget {
  const StaleBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.df,
        vertical: AppSpacing.xs,
      ),
      color: AppColors.warning.withValues(alpha: 0.12),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(
            Icons.cloud_off_rounded,
            size: 14,
            color: AppColors.warning,
          ),
          const SizedBox(width: AppSpacing.xs),
          Flexible(
            child: Text(
              AppLocalizations.get('offlineShowingCached'),
              style: AppTextStyles.bodySmall.copyWith(color: AppColors.warning),
            ),
          ),
        ],
      ),
    );
  }
}
