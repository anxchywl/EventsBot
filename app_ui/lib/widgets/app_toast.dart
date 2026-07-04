import 'package:flutter/material.dart';
import 'toast_manager.dart';

/// A utility class for showing toast messages that auto-dismiss.
/// Uses ToastManager for stacking toasts with animations.
class AppToast {
  AppToast._();

  /// Shows a success toast message.
  static void showSuccess(BuildContext context, String message) {
    ToastManager.showSuccess(context, message);
  }

  /// Shows an error toast message.
  static void showError(BuildContext context, String message) {
    ToastManager.showError(context, message);
  }

  /// Shows a warning toast message.
  static void showWarning(BuildContext context, String message) {
    ToastManager.showWarning(context, message);
  }

  /// Shows an info toast message.
  static void showInfo(BuildContext context, String message) {
    ToastManager.showInfo(context, message);
  }
}
