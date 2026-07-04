# App UI Kit

A shareable, reusable Flutter UI Kit with design tokens, widgets, and components.
Built for students & developers who want a ready-made design system for their Flutter apps.

## Features

- **Design Tokens** — colors, typography, spacing, icons — all in one place
- **46 public symbols** — buttons, inputs, cards, dialogs, loaders, toasts, and more
- **SVG + Material icon system** — unified `AppIcon` widget renders both seamlessly
- **Gamification widgets** — level rings, reward toasts, XP progress
- **Fintech widgets** — bank cards with gradients, masked numbers, chip icons
- **Zero business logic** — purely presentational, accepts data via parameters
- **Light & dark theme ready**

---

## Getting Started

### 1. Add dependency

In your app's `pubspec.yaml`:

```yaml
dependencies:
  app_ui:
    path: packages/app_ui
```

### 2. Import

```dart
import 'package:app_ui/app_ui.dart';
```

> **Important:** Only import `app_ui.dart`. Never import individual files directly.

### 3. Add assets (optional)

If you use the SVG icon paths defined in `AppIcons`, copy the `assets/icons/` folder
into your project root and declare them in `pubspec.yaml`:

```yaml
flutter:
  assets:
    - assets/icons/
    - assets/avatars/
```

---

## Project Structure

```
lib/
├── app_ui.dart                  # Barrel file — the ONLY public entry point
│
├── tokens/                      # Design tokens
│   ├── app_colors.dart          # 60+ color constants (brand, semantic, neutral, accent, social)
│   ├── app_spacing.dart         # Spacing scale, EdgeInsets helpers, border radii, sizes
│   └── app_text_styles.dart     # Full Material type scale + 15 custom app styles
│
├── icons/                       # Icon system
│   ├── app_icon_data.dart       # Sealed class: SvgIcon | MaterialIcon
│   ├── app_icon.dart            # Unified AppIcon widget + size presets
│   └── app_icons.dart           # 170+ icon constants organized by category
│
├── buttons/                     # Button components
│   ├── app_primary_button.dart  # Filled CTA button with loading state
│   ├── app_secondary_button.dart# Outlined secondary button
│   ├── app_text_button.dart     # Text-only button with underline mode
│   └── app_icon_button.dart     # Icon-only button with background option
│
├── inputs/                      # Form inputs
│   ├── app_text_field.dart      # Standard text input
│   ├── app_password_field.dart  # Password with visibility toggle
│   ├── app_search_field.dart    # Search input with clear button
│   ├── app_otp_field.dart       # OTP/PIN box input (paste-aware)
│   └── app_phone_field.dart     # Phone number with country code
│
├── cards/                       # Card components
│   ├── app_card.dart            # Generic card + AppCardWithHeader
│   ├── app_user_card.dart       # User card with avatar & verified badge
│   ├── app_job_card.dart        # Job listing card with tags & salary
│   ├── app_bank_card.dart       # Fintech bank card with gradient & mask
│   └── app_list_tile.dart       # Settings/menu list tile with chevron
│
├── appbars/
│   └── app_app_bar.dart         # AppAppBar & AppSimpleAppBar
│
├── dialogs/
│   ├── app_bottom_sheet.dart    # Bottom sheets: custom, selection, confirmation
│   └── app_confirm_dialog.dart  # Alert & confirm dialog helpers
│
├── indicators/                  # Loading & progress
│   ├── app_loader.dart          # Spinner with size variants + overlay
│   ├── app_progress_bar.dart    # Linear bar + step progress
│   └── app_level_ring.dart      # Circular XP ring + circular progress
│
└── widgets/                     # Toasts & overlays
    ├── app_toast.dart           # Success/error/warning/info toast façade
    ├── toast_manager.dart       # Stacking overlay toast manager
    └── reward_toast.dart        # Gamification reward & level-up toasts
```

---

## Design Tokens

### Colors

`AppColors` provides 60+ named color constants, organized by purpose:

```dart
// Brand
Container(color: AppColors.primary)        // Vibrant purple
Container(color: AppColors.primaryLight)   // Light purple background

// Semantic
Text('OK', style: TextStyle(color: AppColors.green))    // Success
Text('!',  style: TextStyle(color: AppColors.red))      // Error
Text('⚠',  style: TextStyle(color: AppColors.orange))   // Warning

// Neutral
Container(color: AppColors.backgroundGrey) // Light background
Container(color: AppColors.borderGrey)     // Dividers & borders

// Social
Icon(Icons.facebook, color: AppColors.facebook)
Icon(Icons.telegram, color: AppColors.telegram)

// Gradients
Container(
  decoration: BoxDecoration(
    gradient: LinearGradient(colors: AppColors.primaryGradient),
  ),
)
```

### Spacing

`AppSpacing` defines a consistent spacing scale and helper EdgeInsets:

```dart
// Scale: xxs(2) xs(4) sm(8) md(12) lg(16) xl(24) xxl(32) xxxl(48)
SizedBox(height: AppSpacing.md)         // 12px gap
SizedBox(width: AppSpacing.lg)          // 16px gap

// Pre-built EdgeInsets
Padding(padding: AppSpacing.screenPadding)    // 16px horizontal
Padding(padding: AppSpacing.cardInsets)       // 16px all-around
Padding(padding: AppSpacing.paddingAllSm)     // 8px all-around

// SizedBox helpers
AppSpacing.gapH8       // SizedBox(height: 8)
AppSpacing.gapW16      // SizedBox(width: 16)

// Border radii
Container(
  decoration: BoxDecoration(
    borderRadius: AppSpacing.radiusMd,   // 12px
  ),
)
```

### Typography

`AppTextStyles` provides the full Material 3 type scale plus 15 custom styles:

```dart
// Material type scale
Text('Title',   style: AppTextStyles.headlineMedium)
Text('Body',    style: AppTextStyles.bodyMedium)
Text('Caption', style: AppTextStyles.labelSmall)

// Custom app styles
Text('SEND',    style: AppTextStyles.button)
Text('₸12,500', style: AppTextStyles.amount)
Text('1234 **** **** 5678', style: AppTextStyles.cardNumber)
Text('Section', style: AppTextStyles.sectionHeader)
Text('2 min ago', style: AppTextStyles.timestamp)
```

### Icons

The icon system uses a sealed class (`AppIconData`) so you never need to know
whether an icon is SVG or Material. Just pass it to `AppIcon`:

```dart
// SVG icon
AppIcon(AppIcons.home)

// Material icon
AppIcon(AppIcons.settingsIcon)

// Customized
AppIcon(AppIcons.notifications, size: 28, color: AppColors.red)

// Size presets via extension
AppIcon.small(AppIcons.home)     // 16px
AppIcon.medium(AppIcons.home)    // 24px
AppIcon.large(AppIcons.home)     // 32px
AppIcon.xl(AppIcons.home)        // 48px
```

---

## Widgets

### Buttons

```dart
// Primary (filled) — main CTA
AppPrimaryButton(
  label: 'Continue',
  onPressed: () {},
  isLoading: false,
  size: AppButtonSize.large,
)

// Secondary (outlined)
AppSecondaryButton(
  label: 'Cancel',
  onPressed: () {},
)

// Text button
AppTextButton(
  label: 'Skip',
  onPressed: () {},
  isUnderlined: true,
)

// Icon button
AppIconButton(
  icon: AppIcons.close,
  onPressed: () {},
  size: AppIconButtonSize.medium,
  hasBackground: true,
)
```

### Inputs

```dart
// Text field
AppTextField(
  label: 'Email',
  hint: 'you@example.com',
  controller: _ctrl,
  validator: (v) => v!.isEmpty ? 'Required' : null,
)

// Password field (with visibility toggle)
AppPasswordField(
  label: 'Password',
  controller: _passCtrl,
)

// Search field (with auto-clear button)
AppSearchField(
  hint: 'Search...',
  onChanged: (q) => _filter(q),
)

// OTP/PIN field
AppOtpField(
  length: 4,
  onCompleted: (pin) => _verifyPin(pin),
)

// Phone field
AppPhoneField(
  label: 'Phone',
  controller: _phoneCtrl,
  countryCode: '+7',
  onCountryCodeTap: () => _showPicker(),
)
```

### Cards

```dart
// Generic card
AppCard(
  onTap: () {},
  child: Text('Hello'),
)

// Card with header
AppCardWithHeader(
  title: 'Settings',
  subtitle: 'Account preferences',
  trailing: AppIcon(AppIcons.chevronRight),
  child: settingsContent,
)

// User card
AppUserCard(
  name: 'Alice',
  subtitle: 'Online',
  avatarUrl: 'https://...',
  isVerified: true,
  onTap: () {},
)

// Job card
AppJobCard(
  title: 'Flutter Developer',
  company: 'Tech Corp',
  location: 'Astana',
  salary: '500 000 ₸',
  tags: ['Remote', 'Full-time'],
  isPromoted: true,
)

// Bank card
AppBankCard(
  cardNumber: '4111111111111111',
  holderName: 'ALICE SMITH',
  expiryDate: '12/27',
  balance: 125000,
  type: BankCardType.visa,
)

// List tile
AppListTile(
  leading: AppIcon(AppIcons.settingsIcon),
  title: 'Language',
  subtitle: 'English',
  showChevron: true,
  onTap: () {},
)
```

### App Bars

```dart
// Full-featured
AppAppBar(
  title: 'Profile',
  showBackButton: true,
  actions: [AppIconButton(icon: AppIcons.edit, onPressed: () {})],
)

// Simple (title + back)
AppSimpleAppBar(title: 'Details')
```

### Dialogs & Bottom Sheets

```dart
// Custom bottom sheet
AppBottomSheet.show(
  context: context,
  title: 'Options',
  child: myContent,
);

// Selection bottom sheet
final result = await AppBottomSheet.showSelection<String>(
  context: context,
  title: 'Choose Language',
  options: [
    AppBottomSheetOption(title: 'English', value: 'en'),
    AppBottomSheetOption(title: 'Русский', value: 'ru'),
    AppBottomSheetOption(title: 'Қазақша', value: 'kk'),
  ],
);

// Confirmation dialog
final confirmed = await AppConfirmDialog.show(
  context: context,
  title: 'Delete?',
  message: 'This action cannot be undone.',
  confirmLabel: 'Delete',
  isDestructive: true,
);

// Alert dialog (OK only)
await AppConfirmDialog.showAlert(
  context: context,
  title: 'Success',
  message: 'Your profile was saved.',
);
```

### Loaders & Progress

```dart
// Spinner
AppLoader()
AppLoader(size: AppLoaderSize.large)
AppLoader.centered()        // Centered in parent

// Show/hide loading overlay dialog
AppLoader.showDialog(context);
AppLoader.hideDialog(context);

// Linear progress bar
AppProgressBar(
  progress: 0.65,
  label: 'Uploading…',
  showPercentage: true,
)

// Step progress
AppStepProgress(currentStep: 2, totalSteps: 5)

// Circular XP / Level ring
AppLevelRing(
  progress: 0.72,
  level: 5,
  size: 80,
)

// Simple circular progress
AppCircularProgress(progress: 0.45, size: 60)
```

### Toasts

```dart
// Simple toasts
AppToast.showSuccess(context, 'Saved!');
AppToast.showError(context, 'Something went wrong');
AppToast.showWarning(context, 'Low battery');
AppToast.showInfo(context, 'New update available');

// Gamification reward toast
RewardToastManager.show(
  context: context,
  type: RewardToastType.reward,
  reward: RewardItem(
    title: 'Daily Login',
    xpAmount: 50,
    bonusAmount: 100,
  ),
);

// Level-up toast
RewardToastManager.show(
  context: context,
  type: RewardToastType.levelUp,
  levelUp: LevelUpData(previousLevel: 4, newLevel: 5),
);
```

---

## Guidelines

1. **Single entry point** — only `import 'package:app_ui/app_ui.dart';`
2. **No direct styling in features** — use `AppColors`, `AppSpacing`, `AppTextStyles`
3. **No `Colors.*`, `Icons.*`, raw `TextStyle()` in feature code** — use tokens
4. **No business logic in the UI kit** — components are purely presentational
5. **Components accept data via constructor parameters only**
6. **All widgets support light and dark themes**

