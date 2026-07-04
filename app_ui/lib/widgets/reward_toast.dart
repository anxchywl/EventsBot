import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import '../tokens/app_colors.dart';
import '../icons/app_icons.dart';
import '../icons/app_icon.dart';

/// Reward data for display in toast
class RewardItem {
  final String title;
  final int xpAmount;
  final int bonusAmount;
  final int tokenAmount;
  final AppIconData? icon;
  final Color? iconColor;

  const RewardItem({
    required this.title,
    this.xpAmount = 0,
    this.bonusAmount = 0,
    this.tokenAmount = 0,
    this.icon,
    this.iconColor,
  });
}

/// Level up data for display
class LevelUpData {
  final int previousLevel;
  final int newLevel;
  final String? localizedTitle;
  final String? localizedLevelLabel;

  const LevelUpData({
    required this.previousLevel,
    required this.newLevel,
    this.localizedTitle,
    this.localizedLevelLabel,
  });
}

/// Toast types for different styles
enum RewardToastType { reward, levelUp }

/// Individual toast data
class _RewardToastData {
  final String id;
  final RewardToastType type;
  final DateTime createdAt;
  
  // For reward type
  final RewardItem? reward;
  
  // For level up type
  final LevelUpData? levelUp;

  _RewardToastData.reward({
    required this.id,
    required this.reward,
  }) : type = RewardToastType.reward,
       levelUp = null,
       createdAt = DateTime.now();

  _RewardToastData.levelUp({
    required this.id,
    required this.levelUp,
  }) : type = RewardToastType.levelUp,
       reward = null,
       createdAt = DateTime.now();
}

/// A toast manager for showing beautiful reward toasts with rich UI.
/// Features:
/// - Shows reward name, XP, bonus, tokens on separate lines with icons
/// - Special level up toast displayed separately
/// - Smooth animations and swipe to dismiss
class RewardToastManager {
  RewardToastManager._();

  static OverlayEntry? _overlayEntry;
  static final LinkedHashMap<String, _RewardToastData> _toastsMap = LinkedHashMap();
  static final GlobalKey<_RewardToastOverlayState> _overlayKey = GlobalKey();
  static int _idCounter = 0;

  static String _generateId() => 'reward_toast_${++_idCounter}';

  /// Shows a reward toast with rich formatting
  static void showReward(BuildContext context, RewardItem reward) {
    final toast = _RewardToastData.reward(
      id: _generateId(),
      reward: reward,
    );
    _show(context, toast);
  }

  /// Shows a level up celebration toast
  static void showLevelUp(
    BuildContext context,
    int previousLevel,
    int newLevel, {
    String? localizedTitle,
    String? localizedLevelLabel,
  }) {
    final toast = _RewardToastData.levelUp(
      id: _generateId(),
      levelUp: LevelUpData(
        previousLevel: previousLevel,
        newLevel: newLevel,
        localizedTitle: localizedTitle,
        localizedLevelLabel: localizedLevelLabel,
      ),
    );
    _show(context, toast, duration: const Duration(seconds: 5));
  }

  static void _show(BuildContext context, _RewardToastData toast, {Duration duration = const Duration(seconds: 4)}) {
    // Dismiss keyboard first
    FocusScope.of(context).unfocus();

    // Small delay to let keyboard dismiss
    Future.delayed(const Duration(milliseconds: 100), () {
      if (!context.mounted) return;
      
      _toastsMap[toast.id] = toast;

      if (_overlayEntry == null) {
        _overlayEntry = OverlayEntry(
          builder: (ctx) => _RewardToastOverlay(
            key: _overlayKey,
            initialToasts: _toastsMap.values.toList().reversed.toList(),
            onDismiss: (id) => _dismissToast(id),
          ),
        );
        Overlay.of(context).insert(_overlayEntry!);
      } else {
        _overlayKey.currentState?.addToast(toast);
      }

      // Auto-dismiss
      Future.delayed(duration, () {
        _dismissToast(toast.id);
      });
    });
  }

  static void _dismissToast(String id) {
    if (_toastsMap.containsKey(id)) {
      _toastsMap.remove(id);
      _overlayKey.currentState?.removeToast(id);

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

/// The overlay widget that renders all toasts
class _RewardToastOverlay extends StatefulWidget {
  final List<_RewardToastData> initialToasts;
  final void Function(String id) onDismiss;

  const _RewardToastOverlay({
    super.key,
    required this.initialToasts,
    required this.onDismiss,
  });

  @override
  State<_RewardToastOverlay> createState() => _RewardToastOverlayState();
}

class _RewardToastOverlayState extends State<_RewardToastOverlay> {
  final GlobalKey<AnimatedListState> _listKey = GlobalKey();
  final List<_RewardToastData> _toasts = [];
  final Set<String> _dismissing = {};

  @override
  void initState() {
    super.initState();
    _toasts.addAll(widget.initialToasts);
  }

  void addToast(_RewardToastData toast) {
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

  Widget _buildToastItem(_RewardToastData toast, Animation<double> animation, {bool isRemoving = false}) {
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
          child: toast.type == RewardToastType.levelUp
              ? _AnimatedLevelUpToast(
                  toast: toast,
                  onDismiss: () => widget.onDismiss(toast.id),
                )
              : _AnimatedRewardToast(
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

/// Animated reward toast widget with swipe physics
class _AnimatedRewardToast extends StatefulWidget {
  final _RewardToastData toast;
  final VoidCallback onDismiss;

  const _AnimatedRewardToast({
    required this.toast,
    required this.onDismiss,
  });

  @override
  State<_AnimatedRewardToast> createState() => _AnimatedRewardToastState();
}

class _AnimatedRewardToastState extends State<_AnimatedRewardToast>
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

  @override
  Widget build(BuildContext context) {
    final opacity = (1 - (_dragOffset.abs() / 200)).clamp(0.5, 1.0);
    final rotation = _dragOffset / 1500;
    final reward = widget.toast.reward!;

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
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    AppColors.green,
                    AppColors.green.withValues(alpha: 0.9),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(14),
                
              ),
              child: Row(
                children: [
                  // Icon
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: AppIcon(
                      reward.icon ?? AppIcons.check,
                      color: Colors.white,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Title and rewards in column
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          reward.title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            height: 1.2,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 4),
                        // Compact rewards row
                        Row(
                          children: [
                            if (reward.xpAmount > 0)
                              _buildCompactReward(AppIcons.starRounded, '+${reward.xpAmount} XP'),
                            if (reward.bonusAmount > 0) ...[
                              if (reward.xpAmount > 0) const SizedBox(width: 10),
                              _buildCompactReward(AppIcons.bonus, '+${reward.bonusAmount}'),
                            ],
                            if (reward.tokenAmount > 0) ...[
                              if (reward.xpAmount > 0 || reward.bonusAmount > 0) const SizedBox(width: 10),
                              _buildCompactReward(AppIcons.token, '+${reward.tokenAmount}', ),
                            ],
                          ],
                        ),
                      ],
                    ),
                  ),
                  // Close button
                  GestureDetector(
                    onTap: widget.onDismiss,
                    behavior: HitTestBehavior.opaque,
                    child: Padding(
                      padding: const EdgeInsets.only(left: 8),
                      child: Icon(
                        Icons.close_rounded,
                        color: Colors.white.withValues(alpha: 0.7),
                        size: 18,
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

  Widget _buildCompactReward(AppIconData iconData, String value) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        AppIcon(iconData, size: 14),
        const SizedBox(width: 3),
        Text(
          value,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.95),
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

/// Animated level up toast widget
class _AnimatedLevelUpToast extends StatefulWidget {
  final _RewardToastData toast;
  final VoidCallback onDismiss;

  const _AnimatedLevelUpToast({
    required this.toast,
    required this.onDismiss,
  });

  @override
  State<_AnimatedLevelUpToast> createState() => _AnimatedLevelUpToastState();
}

class _AnimatedLevelUpToastState extends State<_AnimatedLevelUpToast>
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

  @override
  Widget build(BuildContext context) {
    final opacity = (1 - (_dragOffset.abs() / 200)).clamp(0.5, 1.0);
    final rotation = _dragOffset / 1500;
    final levelUp = widget.toast.levelUp!;

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
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    AppColors.primary,
                    Colors.purple.shade600,
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: [
                  // Celebration icon
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.celebration_rounded,
                      color: Colors.white,
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Level info
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          levelUp.localizedTitle ?? '🎉 Level Up!',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 4),
                        // Level transition row
                        Row(
                          children: [
                            Text(
                              '${levelUp.localizedLevelLabel ?? 'Level'} ${levelUp.previousLevel}',
                              style: TextStyle(
                                color: Colors.white.withValues(alpha: 0.7),
                                fontSize: 12,
                              ),
                            ),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              child: Icon(
                                Icons.arrow_forward_rounded,
                                color: Colors.white.withValues(alpha: 0.8),
                                size: 14,
                              ),
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                '${levelUp.localizedLevelLabel ?? 'Level'} ${levelUp.newLevel}',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  // Close button
                  GestureDetector(
                    onTap: widget.onDismiss,
                    behavior: HitTestBehavior.opaque,
                    child: Padding(
                      padding: const EdgeInsets.only(left: 8),
                      child: Icon(
                        Icons.close_rounded,
                        color: Colors.white.withValues(alpha: 0.7),
                        size: 18,
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
