import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

/// Shows a concise, consistent floating snackbar for lifecycle feedback.
///
/// Every event lifecycle surface (detail, submit, resubmit, manager) routes its
/// error and blocking-guidance messages through this helper so the feedback
/// looks and behaves the same everywhere. Successful transitions are reflected
/// inline (status banners, success views) rather than through popups.
void showEventFeedback(BuildContext context, String message) {
  final messenger = ScaffoldMessenger.maybeOf(context);
  if (messenger == null) return;
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(
          message,
          style: AppTextStyles.bodySmall.copyWith(color: AppColors.white),
        ),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.error,
        duration: const Duration(seconds: 3),
        margin: const EdgeInsets.all(AppSpacing.df),
        shape: RoundedRectangleBorder(borderRadius: HomeRadius.cardBR),
      ),
    );
}
