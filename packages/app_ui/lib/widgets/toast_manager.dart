import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import '../tokens/app_colors.dart';

/// Toast types for different styles
enum ToastType { success, error, warning, info }

/// Individual toast data
class _ToastData {
  final String id;
  final String message;
  final ToastType type;
  final DateTime createdAt;

  _ToastData({
    required this.id,
    required this.message,
    required this.type,
  }) : createdAt = DateTime.now();
}

/// A toast manager that shows beautiful stacking toasts with smooth animations.
/// Features:
/// - Toasts stack from top (newest on top)
/// - Swipe left/right to dismiss with spring physics
/// - Auto-dismiss after 4 seconds
/// - Smooth slide animations when toasts are removed (others slide up)
class ToastManager {
  ToastManager._();

  static OverlayEntry? _overlayEntry;
  static final LinkedHashMap<String, _ToastData> _toastsMap = LinkedHashMap();
  static final GlobalKey<_ToastOverlayState> _overlayKey = GlobalKey();
  static int _idCounter = 0;

  static String _generateId() => 'toast_${++_idCounter}';

  /// Shows a success toast
  static void showSuccess(BuildContext context, String message) {
    _show(context, _cleanMessage(message), ToastType.success);
  }

  /// Shows an error toast
  static void showError(BuildContext context, String message) {
    _show(context, _cleanMessage(message), ToastType.error);
  }

  /// Shows a warning toast
  static void showWarning(BuildContext context, String message) {
    _show(context, _cleanMessage(message), ToastType.warning);
  }

  /// Shows an info toast
  static void showInfo(BuildContext context, String message) {
    _show(context, _cleanMessage(message), ToastType.info);
  }

  /// Clean message by removing "Exception: " prefix
  static String _cleanMessage(String message) {
    if (message.startsWith('Exception: ')) {
      return message.substring(11);
    }
    return message;
  }

  static void _show(BuildContext context, String message, ToastType type) {
    // Dismiss keyboard first to prevent overflow issues
    FocusScope.of(context).unfocus();
    
    final toast = _ToastData(
      id: _generateId(),
      message: message,
      type: type,
    );

    // Small delay to let keyboard dismiss before showing toast
    Future.delayed(const Duration(milliseconds: 100), () {
      if (!context.mounted) return;
      
      // Add to map (newest first in iteration)
      _toastsMap[toast.id] = toast;

      // Create overlay if not exists
      if (_overlayEntry == null) {
        _overlayEntry = OverlayEntry(
          builder: (ctx) => _ToastOverlay(
            key: _overlayKey,
            initialToasts: _toastsMap.values.toList().reversed.toList(),
            onDismiss: (id) => _dismissToast(id),
          ),
        );
        Overlay.of(context).insert(_overlayEntry!);
      } else {
        // Add toast to existing overlay
        _overlayKey.currentState?.addToast(toast);
      }

      // Auto-dismiss after 4 seconds
      Future.delayed(const Duration(seconds: 4), () {
        _dismissToast(toast.id);
      });
    });
  }

  static void _dismissToast(String id) {
    if (_toastsMap.containsKey(id)) {
      _toastsMap.remove(id);
      _overlayKey.currentState?.removeToast(id);

      // Remove overlay when empty after animations complete
      if (_toastsMap.isEmpty) {
        Future.delayed(const Duration(milliseconds: 400), () {
          if (_toastsMap.isEmpty && _overlayEntry != null) {
            _overlayEntry?.remove();
            _overlayEntry = null;
          }
        });
      }
    }
  }
}

/// The overlay widget that renders all toasts with AnimatedList
class _ToastOverlay extends StatefulWidget {
  final List<_ToastData> initialToasts;
  final void Function(String id) onDismiss;

  const _ToastOverlay({
    super.key,
    required this.initialToasts,
    required this.onDismiss,
  });

  @override
  State<_ToastOverlay> createState() => _ToastOverlayState();
}

class _ToastOverlayState extends State<_ToastOverlay> {
  final GlobalKey<AnimatedListState> _listKey = GlobalKey();
  final List<_ToastData> _toasts = [];
  final Set<String> _dismissing = {};

  @override
  void initState() {
    super.initState();
    _toasts.addAll(widget.initialToasts);
  }

  void addToast(_ToastData toast) {
    _toasts.insert(0, toast);
    _listKey.currentState?.insertItem(0, duration: const Duration(milliseconds: 300));
  }

  void removeToast(String id) {
    if (_dismissing.contains(id)) return;
    _dismissing.add(id);

    final index = _toasts.indexWhere((t) => t.id == id);
    if (index != -1) {
      final removed = _toasts.removeAt(index);
      _listKey.currentState?.removeItem(
        index,
        (context, animation) => _buildToastItem(removed, animation, isRemoving: true),
        duration: const Duration(milliseconds: 300),
      );
    }
    _dismissing.remove(id);
  }

  Widget _buildToastItem(_ToastData toast, Animation<double> animation, {bool isRemoving = false}) {
    return SizeTransition(
      sizeFactor: animation,
      child: SlideTransition(
        position: Tween<Offset>(
          begin: isRemoving ? Offset.zero : const Offset(0, -1),
          end: isRemoving ? const Offset(-1, 0) : Offset.zero,
        ).animate(CurvedAnimation(
          parent: animation,
          curve: isRemoving ? Curves.easeIn : Curves.easeOutCubic,
        )),
        child: FadeTransition(
          opacity: animation,
          child: _AnimatedToast(
            toast: toast,
            onDismiss: () => widget.onDismiss(toast.id),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      top: MediaQuery.of(context).padding.top + 16,
      left: 16,
      right: 16,
      child: Material(
        color: Colors.transparent,
        child: AnimatedList(
          key: _listKey,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          initialItemCount: _toasts.length,
          itemBuilder: (context, index, animation) {
            if (index >= _toasts.length) return const SizedBox.shrink();
            return _buildToastItem(_toasts[index], animation);
          },
        ),
      ),
    );
  }
}

/// Individual animated toast widget with spring physics for swipe
class _AnimatedToast extends StatefulWidget {
  final _ToastData toast;
  final VoidCallback onDismiss;

  const _AnimatedToast({
    required this.toast,
    required this.onDismiss,
  });

  @override
  State<_AnimatedToast> createState() => _AnimatedToastState();
}

class _AnimatedToastState extends State<_AnimatedToast>
    with SingleTickerProviderStateMixin {
  late AnimationController _dragController;
  Animation<double>? _dragAnimation;
  double _dragOffset = 0;
  bool _isDismissing = false;

  @override
  void initState() {
    super.initState();
    _dragController = AnimationController.unbounded(vsync: this);
    _dragController.addListener(() {
      if (_dragAnimation != null) {
        setState(() {
          _dragOffset = _dragAnimation!.value;
        });
      }
    });
  }

  @override
  void dispose() {
    _dragController.dispose();
    super.dispose();
  }

  void _onDragUpdate(DragUpdateDetails details) {
    if (_isDismissing) return;
    _dragController.stop();
    setState(() {
      _dragOffset += details.delta.dx;
    });
  }

  void _onDragEnd(DragEndDetails details) {
    if (_isDismissing) return;

    final velocity = details.velocity.pixelsPerSecond.dx;
    
    // Dismiss threshold: dragged far enough OR high velocity swipe
    if (_dragOffset.abs() > 100 || velocity.abs() > 800) {
      _isDismissing = true;
      final targetOffset = _dragOffset > 0 ? 400.0 : -400.0;
      
      _dragAnimation = Tween<double>(begin: _dragOffset, end: targetOffset).animate(
        CurvedAnimation(parent: _dragController, curve: Curves.easeOut),
      );
      _dragController.value = 0;
      _dragController.animateTo(
        1,
        duration: const Duration(milliseconds: 200),
      ).then((_) {
        if (mounted) widget.onDismiss();
      });
    } else {
      // Spring back to center with physics
      final simulation = SpringSimulation(
        SpringDescription.withDampingRatio(
          mass: 1,
          stiffness: 500,
          ratio: 0.7,
        ),
        _dragOffset,
        0,
        velocity / 1000,
      );

      _dragAnimation = _dragController.drive(
        Tween<double>(begin: _dragOffset, end: 0),
      );
      
      _dragController.value = 0;
      _dragController.animateWith(simulation).then((_) {
        if (mounted) {
          setState(() {
            _dragOffset = 0;
          });
        }
      });
    }
  }

  Color _getBackgroundColor() {
    switch (widget.toast.type) {
      case ToastType.success:
        return AppColors.green;
      case ToastType.error:
        return const Color(0xFFE53935);
      case ToastType.warning:
        return AppColors.orange;
      case ToastType.info:
        return AppColors.primary;
    }
  }

  IconData _getIcon() {
    switch (widget.toast.type) {
      case ToastType.success:
        return Icons.check_circle_rounded;
      case ToastType.error:
        return Icons.error_rounded;
      case ToastType.warning:
        return Icons.warning_rounded;
      case ToastType.info:
        return Icons.info_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final opacity = (1 - (_dragOffset.abs() / 200)).clamp(0.5, 1.0);
    final rotation = _dragOffset / 1500; // Subtle rotation on drag

    return GestureDetector(
      onHorizontalDragUpdate: _onDragUpdate,
      onHorizontalDragEnd: _onDragEnd,
      child: Transform.translate(
        offset: Offset(_dragOffset, 0),
        child: Transform.rotate(
          angle: rotation,
          child: Opacity(
            opacity: opacity,
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              decoration: BoxDecoration(
                color: _getBackgroundColor(),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: [
                  Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      _getIcon(),
                      color: Colors.white,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      widget.toast.message,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        height: 1.3,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: widget.onDismiss,
                    behavior: HitTestBehavior.opaque,
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      child: Icon(
                        Icons.close_rounded,
                        color: Colors.white.withValues(alpha: 0.8),
                        size: 20,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
