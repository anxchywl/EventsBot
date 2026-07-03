import 'package:lucide_flutter/lucide_flutter.dart';

import '../icons/app_icon_data.dart';

// Re-export AppIconData types for consumers
export '../icons/app_icon_data.dart';

/// App Icons — single authoritative source for the entire application.
///
/// Design language: SF Symbols visual language via Lucide.
/// Every constant is deliberately chosen; dead aliases are not kept.
///
/// Custom SVG assets (only 3 remain — campus brand marks):
///   assets/logo.svg         — app brand
///   assets/icons/token.svg  — campus digital token
///   assets/icons/bonus.svg  — campus bonus/coin
///
/// Size scale:
///   16 — helper / meta
///   20 — secondary actions, input adornments
///   24 — standard (AppIcon default)
///   28 — feature card headers
///   32–36 — hero service icons
abstract class AppIcons {
  // ─────────────────────────────────────────────────────────────────────────
  // PRIVATE PATHS
  // ─────────────────────────────────────────────────────────────────────────

  static const String _base = 'assets';
  static const String _icons = 'assets/icons';
  static const String _avatars = 'assets/avatars';

  // ─────────────────────────────────────────────────────────────────────────
  // BRAND ASSETS  (SVG — render with original colours; do not tint)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData logo   = SvgIcon('$_base/logo.svg');
  static const AppIconData token  = SvgIcon('$_icons/token.svg');
  static const AppIconData bonus  = SvgIcon('$_icons/bonus.svg');
  static const AppIconData points = SvgIcon('$_icons/bonus.svg');

  // ─────────────────────────────────────────────────────────────────────────
  // NAVIGATION  (SF: house · chevron · xmark · square.grid.2x2)
  // ─────────────────────────────────────────────────────────────────────────

  /// Home tab — bottom nav (SF: house.fill).
  static const AppIconData home = MaterialIcon(LucideIcons.house);

  /// Back navigation (SF: chevron.left / arrow.left).
  static const AppIconData back = MaterialIcon(LucideIcons.arrowLeft);

  /// Dismiss / close (SF: xmark).
  static const AppIconData close = MaterialIcon(LucideIcons.x);

  /// Hamburger menu (SF: line.3.horizontal).
  static const AppIconData menu = MaterialIcon(LucideIcons.menu);

  /// Hub tab — service grid (SF: square.grid.2x2).
  static const AppIconData hub = MaterialIcon(LucideIcons.layoutGrid);

  static const AppIconData chevronRight = MaterialIcon(LucideIcons.chevronRight);
  static const AppIconData chevronLeft  = MaterialIcon(LucideIcons.chevronLeft);
  static const AppIconData chevronUp    = MaterialIcon(LucideIcons.chevronUp);
  static const AppIconData chevronDown  = MaterialIcon(LucideIcons.chevronDown);
  static const AppIconData moreVert     = MaterialIcon(LucideIcons.moreVertical);
  static const AppIconData moreHoriz    = MaterialIcon(LucideIcons.moreHorizontal);

  // ─────────────────────────────────────────────────────────────────────────
  // ACTIONS  (SF: pencil · trash · share · magnifyingglass)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData edit        = MaterialIcon(LucideIcons.pencil);

  /// Edit profile (SF: person.crop.circle.badge.pencil).
  static const AppIconData editProfile = MaterialIcon(LucideIcons.userPen);

  static const AppIconData delete   = MaterialIcon(LucideIcons.trash2);
  static const AppIconData save     = MaterialIcon(LucideIcons.save);
  static const AppIconData copy     = MaterialIcon(LucideIcons.copy);
  static const AppIconData search   = MaterialIcon(LucideIcons.search);

  /// Filter controls (SF: slider.horizontal.3).
  static const AppIconData filter   = MaterialIcon(LucideIcons.slidersHorizontal);

  static const AppIconData share    = MaterialIcon(LucideIcons.share2);
  static const AppIconData add      = MaterialIcon(LucideIcons.plus);
  static const AppIconData addCircle = MaterialIcon(LucideIcons.plusCircle);

  /// Clear / close small (SF: xmark.circle.fill).
  static const AppIconData clear    = MaterialIcon(LucideIcons.x);

  static const AppIconData check      = MaterialIcon(LucideIcons.check);

  /// Filled check circle (SF: checkmark.circle.fill).
  static const AppIconData checkCircle = MaterialIcon(LucideIcons.checkCircle2);

  /// Double-check / mark all read (SF: checkmark.seal).
  static const AppIconData markAsRead = MaterialIcon(LucideIcons.checkCheck);
  static const AppIconData doneAll    = MaterialIcon(LucideIcons.checkCheck);

  static const AppIconData send       = MaterialIcon(LucideIcons.send);
  static const AppIconData attach     = MaterialIcon(LucideIcons.paperclip);
  static const AppIconData logout     = MaterialIcon(LucideIcons.logOut);
  static const AppIconData arrowForward = MaterialIcon(LucideIcons.arrowRight);

  // ─────────────────────────────────────────────────────────────────────────
  // VISIBILITY  (SF: eye · eye.slash)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData visibility    = MaterialIcon(LucideIcons.eye);
  static const AppIconData visibilityOff = MaterialIcon(LucideIcons.eyeOff);

  // ─────────────────────────────────────────────────────────────────────────
  // PROFILE & USER  (SF: person.circle · person · person.2 · camera)
  // ─────────────────────────────────────────────────────────────────────────

  /// Profile tab / avatar (SF: person.circle.fill).
  static const AppIconData profile = MaterialIcon(LucideIcons.circleUser);

  /// Generic person placeholder (SF: person).
  static const AppIconData user    = MaterialIcon(LucideIcons.user);

  /// Multiple users / group (SF: person.2.fill).
  static const AppIconData users   = MaterialIcon(LucideIcons.users);

  /// Add person / follow (SF: person.badge.plus).
  static const AppIconData addAvatar = MaterialIcon(LucideIcons.userPlus);

  static const AppIconData camera  = MaterialIcon(LucideIcons.camera);
  static const AppIconData gallery = MaterialIcon(LucideIcons.image);

  /// Biometric / fingerprint (SF: touchid).
  static const AppIconData faceId  = MaterialIcon(LucideIcons.fingerprint);

  /// Avatar template chooser — layout grid of options.
  static const AppIconData avatarIcon = MaterialIcon(LucideIcons.layout);

  // Semantic aliases used in feature code
  static const AppIconData friends = MaterialIcon(LucideIcons.users);
  static const AppIconData people  = MaterialIcon(LucideIcons.users);

  /// Star grade / rating (SF: star.fill).
  static const AppIconData grade   = MaterialIcon(LucideIcons.star);

  // ─────────────────────────────────────────────────────────────────────────
  // GAMIFICATION  (SF: trophy · star · flame · sparkles · gauge)
  // ─────────────────────────────────────────────────────────────────────────

  /// Heartbeat / pulse activity (SF: waveform.path.ecg).
  static const AppIconData activity   = MaterialIcon(LucideIcons.activity);

  static const AppIconData trophy     = MaterialIcon(LucideIcons.trophy);

  /// Awards — semantic alias for trophy.
  static const AppIconData awards     = MaterialIcon(LucideIcons.trophy);

  /// Leaderboard / rankings chart (SF: chart.bar.fill).
  static const AppIconData leaderboard = MaterialIcon(LucideIcons.barChart2);

  /// Level / progress gauge (SF: gauge.with.dots.needle.bottom.50percent).
  static const AppIconData level      = MaterialIcon(LucideIcons.gauge);

  static const AppIconData star       = MaterialIcon(LucideIcons.star);
  static const AppIconData starRounded = MaterialIcon(LucideIcons.star);

  /// Goal / target (SF: target).
  static const AppIconData target     = MaterialIcon(LucideIcons.target);
  static const AppIconData motivation = MaterialIcon(LucideIcons.target);

  /// Task / checklist item (SF: checkmark.rectangle).
  static const AppIconData task  = MaterialIcon(LucideIcons.clipboardCheck);
  static const AppIconData tasks = MaterialIcon(LucideIcons.clipboardCheck);

  /// Achievement gem (SF: diamond.fill).
  static const AppIconData gem     = MaterialIcon(LucideIcons.gem);
  static const AppIconData diamond = MaterialIcon(LucideIcons.gem);

  /// Fire / streak (SF: flame.fill).
  static const AppIconData flame    = MaterialIcon(LucideIcons.flame);

  /// Premium / special (SF: sparkles).
  static const AppIconData sparkles = MaterialIcon(LucideIcons.sparkles);

  static const AppIconData gift = MaterialIcon(LucideIcons.gift);

  /// Book — tutorials, learning (SF: book.fill).
  static const AppIconData book = MaterialIcon(LucideIcons.bookOpen);

  /// Clipboard list (SF: list.clipboard).
  static const AppIconData assignment = MaterialIcon(LucideIcons.clipboardList);

  // ─────────────────────────────────────────────────────────────────────────
  // FEATURES  (SF: bubble.left · bell · doc.text · arrow.left.arrow.right)
  // ─────────────────────────────────────────────────────────────────────────

  /// Chat bubble (SF: bubble.left.fill).
  static const AppIconData chat = MaterialIcon(LucideIcons.messageCircle);

  /// Message / inbox (SF: message.fill).
  static const AppIconData message = MaterialIcon(LucideIcons.messageSquare);

  /// Notification bell (SF: bell.fill).
  static const AppIconData notification = MaterialIcon(LucideIcons.bell);

  /// Course / open book (SF: books.vertical.fill).
  static const AppIconData course = MaterialIcon(LucideIcons.bookOpen);

  /// Transfer / swap (SF: arrow.left.arrow.right).
  static const AppIconData transfer = MaterialIcon(LucideIcons.arrowLeftRight);

  /// Statistics chart (SF: chart.bar.xaxis).
  static const AppIconData statistics = MaterialIcon(LucideIcons.barChart2);

  /// Document (SF: doc.text.fill).
  static const AppIconData document = MaterialIcon(LucideIcons.fileText);

  /// File request / inquiry (SF: questionmark.folder.fill).
  static const AppIconData request = MaterialIcon(LucideIcons.fileQuestion);

  static const AppIconData heart  = MaterialIcon(LucideIcons.heart);
  static const AppIconData fintech = MaterialIcon(LucideIcons.trendingUp);
  static const AppIconData wallet  = MaterialIcon(LucideIcons.wallet);

  // ─────────────────────────────────────────────────────────────────────────
  // EMERGENCY / SOS  (SF: shield.exclamationmark · heart.circle · flame)
  // ─────────────────────────────────────────────────────────────────────────

  /// Emergency shield (SF: shield.exclamationmark.fill).
  static const AppIconData shieldAlert = MaterialIcon(LucideIcons.shieldAlert);

  /// Medical / ambulance heartbeat (SF: heart.text.clipboard).
  static const AppIconData heartPulse = MaterialIcon(LucideIcons.heartPulse);

  // ─────────────────────────────────────────────────────────────────────────
  // SOCIAL MEDIA  (Lucide semantic equivalents, rendered with brand colours)
  // No brand SVGs — use tinted Lucide icons with SocialPlatform.color
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData instagram = MaterialIcon(LucideIcons.camera);
  static const AppIconData whatsapp  = MaterialIcon(LucideIcons.messageCircle);
  static const AppIconData twitter   = MaterialIcon(LucideIcons.send);
  static const AppIconData facebook  = MaterialIcon(LucideIcons.users);
  static const AppIconData telegram  = MaterialIcon(LucideIcons.send);

  // ─────────────────────────────────────────────────────────────────────────
  // SETTINGS & SECURITY  (SF: gearshape · shield.checkmark · lock · globe)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData settings = MaterialIcon(LucideIcons.settings);
  static const AppIconData security = MaterialIcon(LucideIcons.shieldCheck);
  static const AppIconData language = MaterialIcon(LucideIcons.globe);

  /// Theme / appearance toggle (SF: circle.lefthalf.filled).
  static const AppIconData theme    = MaterialIcon(LucideIcons.sunMoon);

  static const AppIconData lock     = MaterialIcon(LucideIcons.lock);
  static const AppIconData lockOpen = MaterialIcon(LucideIcons.lockOpen);

  // ─────────────────────────────────────────────────────────────────────────
  // STATUS / FEEDBACK  (SF: checkmark · exclamationmark.circle · info)
  // ─────────────────────────────────────────────────────────────────────────

  /// Error / alert circle (SF: exclamationmark.circle.fill).
  static const AppIconData error       = MaterialIcon(LucideIcons.alertCircle);
  static const AppIconData alertCircle = MaterialIcon(LucideIcons.alertCircle);

  /// Warning triangle (SF: exclamationmark.triangle.fill).
  static const AppIconData warning  = MaterialIcon(LucideIcons.alertTriangle);

  /// Informational (SF: info.circle.fill).
  static const AppIconData info     = MaterialIcon(LucideIcons.info);

  // ─────────────────────────────────────────────────────────────────────────
  // WEATHER  (SF: sun.max · moon.fill · wind · cloud.sun.fill)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData sun  = MaterialIcon(LucideIcons.sun);
  static const AppIconData moon = MaterialIcon(LucideIcons.moon);
  static const AppIconData wind = MaterialIcon(LucideIcons.wind);

  // ─────────────────────────────────────────────────────────────────────────
  // MEDIA  (SF: photo · video · play.circle)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData image = MaterialIcon(LucideIcons.image);
  static const AppIconData video = MaterialIcon(LucideIcons.video);

  // ─────────────────────────────────────────────────────────────────────────
  // EDUCATION  (SF: graduationcap · megaphone · arrow.up.right.square)
  // ─────────────────────────────────────────────────────────────────────────

  /// Graduation cap (SF: graduationcap.fill).
  static const AppIconData school    = MaterialIcon(LucideIcons.graduationCap);

  /// Classroom / presentation screen (SF: display).
  static const AppIconData classroom = MaterialIcon(LucideIcons.monitor);

  /// Gym / fitness (SF: figure.run).
  static const AppIconData gym       = MaterialIcon(LucideIcons.dumbbell);

  /// Door / physical access (SF: door.left.hand.open).
  static const AppIconData doorOpen  = MaterialIcon(LucideIcons.doorOpen);

  /// Announcement (SF: megaphone.fill).
  static const AppIconData megaphone = MaterialIcon(LucideIcons.megaphone);

  /// Open in browser (SF: arrow.up.right.square).
  static const AppIconData openInNew = MaterialIcon(LucideIcons.externalLink);

  // ─────────────────────────────────────────────────────────────────────────
  // HUB SERVICES  — each icon immediately communicates the feature
  // ─────────────────────────────────────────────────────────────────────────

  /// Dining / meal program (SF: fork.knife).
  static const AppIconData utensils  = MaterialIcon(LucideIcons.utensils);

  /// Job search / career (SF: briefcase.fill).
  static const AppIconData briefcase = MaterialIcon(LucideIcons.briefcase);

  /// Financial growth (SF: chart.line.uptrend.xyaxis).
  static const AppIconData trendingUp = MaterialIcon(LucideIcons.trendingUp);
  static const AppIconData trending   = MaterialIcon(LucideIcons.trendingUp);

  // ─────────────────────────────────────────────────────────────────────────
  // CALENDAR / TIME  (SF: calendar · clock · arrow.counterclockwise)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData calendar     = MaterialIcon(LucideIcons.calendar);
  static const AppIconData event        = MaterialIcon(LucideIcons.calendar);
  static const AppIconData calendarMonth = MaterialIcon(LucideIcons.calendarDays);
  static const AppIconData history      = MaterialIcon(LucideIcons.history);
  static const AppIconData time         = MaterialIcon(LucideIcons.clock);

  // ─────────────────────────────────────────────────────────────────────────
  // LOCATION  (SF: mappin.and.ellipse)
  // ─────────────────────────────────────────────────────────────────────────

  /// Map pin (SF: mappin.and.ellipse.fill).
  static const AppIconData location = MaterialIcon(LucideIcons.mapPin);

  // ─────────────────────────────────────────────────────────────────────────
  // COMMUNICATION  (SF: envelope · phone · phone.fill)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData email = MaterialIcon(LucideIcons.mail);
  static const AppIconData phone = MaterialIcon(LucideIcons.phone);
  static const AppIconData call  = MaterialIcon(LucideIcons.phoneCall);

  // ─────────────────────────────────────────────────────────────────────────
  // CONTENT  (SF: link · qrcode)
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData link   = MaterialIcon(LucideIcons.link);
  static const AppIconData qrCode = MaterialIcon(LucideIcons.qrCode);

  // ─────────────────────────────────────────────────────────────────────────
  // MISC
  // ─────────────────────────────────────────────────────────────────────────

  static const AppIconData refresh = MaterialIcon(LucideIcons.refreshCw);

  // ─────────────────────────────────────────────────────────────────────────
  // AVATAR IMAGE PATHS  (String — use with Image.asset directly)
  // ─────────────────────────────────────────────────────────────────────────

  static const String avatar1Path      = '$_avatars/1.png';
  static const String avatar2Path      = '$_avatars/2.png';
  static const String avatar3Path      = '$_avatars/3.png';
  static const String avatar4Path      = '$_avatars/4.png';
  static const String defaultAvatarPath = '$_avatars/1.png';
}
