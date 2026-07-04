import 'package:flutter/material.dart';
import '../tokens/app_colors.dart';
import '../tokens/app_spacing.dart';
import '../tokens/app_text_styles.dart';

/// Bank card widget for fintech features.
/// 
/// Example:
/// ```dart
/// AppBankCard(
///   cardNumber: '4111 1111 1111 1111',
///   holderName: 'John Doe',
///   expiryDate: '12/25',
///   balance: '150,000 KZT',
///   cardType: BankCardType.visa,
/// )
/// ```
class AppBankCard extends StatelessWidget {
  const AppBankCard({
    super.key,
    this.cardNumber,
    this.holderName,
    this.expiryDate,
    this.balance,
    this.cardType = BankCardType.generic,
    this.gradientColors,
    this.onTap,
    this.isCompact = false,
    this.showCardNumber = true,
    this.width,
    this.height,
  });

  /// Card number (will be masked by default).
  final String? cardNumber;

  /// Cardholder name.
  final String? holderName;

  /// Expiry date.
  final String? expiryDate;

  /// Current balance to display.
  final String? balance;

  /// Card type (Visa, Mastercard, etc.).
  final BankCardType cardType;

  /// Custom gradient colors.
  final List<Color>? gradientColors;

  /// Tap callback.
  final VoidCallback? onTap;

  /// Whether to show compact version.
  final bool isCompact;

  /// Whether to show card number.
  final bool showCardNumber;

  /// Custom width.
  final double? width;

  /// Custom height.
  final double? height;

  List<Color> get _gradientColors => gradientColors ?? cardType.gradientColors;

  @override
  Widget build(BuildContext context) {
    final effectiveHeight = height ?? (isCompact ? 120.0 : 200.0);
    final effectiveWidth = width ?? double.infinity;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: effectiveWidth,
        height: effectiveHeight,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: _gradientColors,
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: AppSpacing.borderRadiusLg,
        ),
        child: Padding(
          padding: isCompact ? AppSpacing.cardPaddingSm : AppSpacing.cardPaddingLg,
          child: isCompact ? _buildCompactContent() : _buildFullContent(),
        ),
      ),
    );
  }

  Widget _buildFullContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        // Top row: Card type logo and balance
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            _buildCardTypeLogo(),
            if (balance != null)
              Text(
                balance!,
                style: AppTextStyles.titleLarge.copyWith(
                  color: AppColors.white,
                ),
              ),
          ],
        ),
        // Card number
        if (showCardNumber && cardNumber != null)
          Text(
            _maskedCardNumber,
            style: AppTextStyles.cardNumber.copyWith(
              color: AppColors.white,
            ),
          ),
        // Bottom row: Holder name and expiry
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'CARD HOLDER',
                  style: AppTextStyles.labelSmall.copyWith(
                    color: AppColors.white.withValues(alpha: 0.7),
                  ),
                ),
                AppSpacing.verticalXs,
                Text(
                  holderName ?? 'YOUR NAME',
                  style: AppTextStyles.labelMedium.copyWith(
                    color: AppColors.white,
                  ),
                ),
              ],
            ),
            if (expiryDate != null)
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    'EXPIRES',
                    style: AppTextStyles.labelSmall.copyWith(
                      color: AppColors.white.withValues(alpha: 0.7),
                    ),
                  ),
                  AppSpacing.verticalXs,
                  Text(
                    expiryDate!,
                    style: AppTextStyles.labelMedium.copyWith(
                      color: AppColors.white,
                    ),
                  ),
                ],
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildCompactContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            _buildCardTypeLogo(),
            if (balance != null)
              Text(
                balance!,
                style: AppTextStyles.titleMedium.copyWith(
                  color: AppColors.white,
                ),
              ),
          ],
        ),
        if (showCardNumber && cardNumber != null)
          Text(
            _shortCardNumber,
            style: AppTextStyles.bodyMedium.copyWith(
              color: AppColors.white.withValues(alpha: 0.8),
              fontFamily: 'monospace',
            ),
          ),
      ],
    );
  }

  Widget _buildCardTypeLogo() {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: AppColors.white.withValues(alpha: 0.2),
        borderRadius: AppSpacing.borderRadiusXs,
      ),
      child: Text(
        cardType.label,
        style: AppTextStyles.labelMedium.copyWith(
          color: AppColors.white,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  String get _maskedCardNumber {
    if (cardNumber == null || cardNumber!.length < 16) {
      return '•••• •••• •••• ••••';
    }
    final clean = cardNumber!.replaceAll(' ', '');
    return '${clean.substring(0, 4)} •••• •••• ${clean.substring(clean.length - 4)}';
  }

  String get _shortCardNumber {
    if (cardNumber == null || cardNumber!.length < 4) {
      return '•••• ••••';
    }
    final clean = cardNumber!.replaceAll(' ', '');
    return '•••• ${clean.substring(clean.length - 4)}';
  }
}

/// Bank card type enum with visual properties.
enum BankCardType {
  visa([Color(0xFF1A1F71), Color(0xFF2E35A8)], 'VISA'),
  mastercard([Color(0xFFEB001B), Color(0xFFF79E1B)], 'MASTERCARD'),
  generic([Color(0xFF7100FF), Color(0xFF4A00E0)], 'CARD'),
  gold([Color(0xFFFFD700), Color(0xFFFFA500)], 'GOLD'),
  platinum([Color(0xFF2C2C2C), Color(0xFF5C5C5C)], 'PLATINUM'),
  debit([Color(0xFF00A86B), Color(0xFF006B4D)], 'DEBIT'),
  credit([Color(0xFF7100FF), Color(0xFF4A00E0)], 'CREDIT');

  const BankCardType(this.gradientColors, this.label);

  final List<Color> gradientColors;
  final String label;
}
