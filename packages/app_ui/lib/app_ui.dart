/// App UI Kit
/// 
/// A comprehensive, shareable UI component library for Flutter applications.
/// 
/// ## Usage
/// 
/// Import the entire UI Kit with a single import:
/// 
/// ```dart
/// import 'package:app_ui/app_ui.dart';
/// ```
/// 
/// ## Design Tokens
/// 
/// Access design tokens through abstract classes:
/// 
/// - [AppColors] - Color palette
/// - [AppIcons] - All icons (SVG paths + Material icons)
/// - [AppSpacing] - Spacing, padding, border radius
/// - [AppTextStyles] - Typography styles
/// 
/// ## Components
/// 
/// ### Buttons
/// - [AppPrimaryButton] - Primary filled button
/// - [AppSecondaryButton] - Outlined button
/// - [AppTextButton] - Text-only button
/// - [AppIconButton] - Icon-only button
/// 
/// ### Inputs
/// - [AppTextField] - Standard text input
/// - [AppPasswordField] - Password with visibility toggle
/// - [AppSearchField] - Search input with clear
/// - [AppOtpField] - OTP/PIN input
/// - [AppPhoneField] - Phone number input
/// 
/// ### Cards
/// - [AppCard] - Generic card container
/// - [AppUserCard] - User display card
/// - [AppJobCard] - Job listing card
/// - [AppBankCard] - Fintech bank card
/// - [AppListTile] - Settings/menu item
/// 
/// ### AppBars
/// - [AppAppBar] - Customizable app bar
/// - [AppSimpleAppBar] - Minimal app bar
/// 
/// ### Dialogs
/// - [AppBottomSheet] - Bottom sheet variants
/// - [AppConfirmDialog] - Confirmation dialogs
/// 
/// ### Indicators
/// - [AppLoader] - Loading spinner
/// - [AppProgressBar] - Linear progress
/// - [AppStepProgress] - Step progress
/// - [AppLevelRing] - Gamification level ring
/// - [AppCircularProgress] - Circular progress
///
/// ### Calendar
/// - [AppCalendar] - Universal premium monthly calendar
/// - [AppCalendarEvent] - Feature-agnostic calendar event model
///
/// ### Widgets
/// - [AppToast] - Toast notification utility
/// - [ToastManager] - Toast stacking manager
library;

// Design Tokens
export 'tokens/app_colors.dart';
export 'tokens/app_spacing.dart';   // includes HomeSpacing
export 'tokens/app_radius.dart';    // HomeRadius
export 'tokens/app_shadows.dart';   // HomeShadows
export 'tokens/app_text_styles.dart';

// Icons (Unified Icon System)
export 'icons/app_icon_data.dart';
export 'icons/app_icon.dart';
export 'icons/app_icons.dart';

// Buttons
export 'buttons/app_primary_button.dart';
export 'buttons/app_secondary_button.dart';
export 'buttons/app_text_button.dart';
export 'buttons/app_icon_button.dart';

// Inputs
export 'inputs/app_text_field.dart';
export 'inputs/app_password_field.dart';
export 'inputs/app_search_bar.dart';
export 'inputs/app_otp_field.dart';
export 'inputs/app_phone_field.dart';

// Cards
export 'cards/app_card.dart';
export 'cards/app_user_card.dart';
export 'cards/app_job_card.dart';
export 'cards/app_bank_card.dart';
export 'cards/app_list_tile.dart';
export 'cards/app_home_card.dart';  // HomeCardStyle

// AppBars
export 'appbars/app_app_bar.dart';

// Dialogs
export 'dialogs/app_bottom_sheet.dart';
export 'dialogs/app_premium_dialog.dart';

// Indicators
export 'indicators/app_loader.dart';
export 'indicators/app_progress_bar.dart';
export 'indicators/app_level_ring.dart';

// Calendar
export 'calendar/app_calendar_event.dart';
export 'calendar/app_calendar.dart';

// Theme
export 'theme/app_theme.dart';  // AppTheme

// Widgets
export 'widgets/app_toast.dart';
export 'widgets/toast_manager.dart';
export 'widgets/reward_toast.dart';
