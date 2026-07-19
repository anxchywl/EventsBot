import 'dart:math';
import 'dart:typed_data';

import 'package:app_ui/app_ui.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../core/auth_store.dart';
import '../../core/cache_store.dart';
import '../../core/exceptions.dart';
import '../../core/localization.dart';
import '../../models/category_model.dart';
import '../../models/event_model.dart';
import 'event_form_validation.dart';

enum _SubmitViewMode {
  form,
  datePicker,
  timePicker,
  endTimePicker,
  categoryPicker,
  success,
}

class SubmitScreen extends StatefulWidget {
  const SubmitScreen({
    super.key,
    this.initialDate,
    this.asSheet = false,
    this.initialEvent,
  });

  /// Optionally pre-fills the event date, e.g. when opened from the shared
  /// calendar for a specific day.
  final DateTime? initialDate;
  final bool asSheet;

  /// When set, the form is opened in edit-and-resubmit mode: fields are
  /// pre-filled with the event's current values and submitting calls the
  /// resubmit endpoint instead of creating a new event.
  final EventModel? initialEvent;

  @override
  State<SubmitScreen> createState() => _SubmitScreenState();
}

class _SubmitScreenState extends State<SubmitScreen> {
  final _formKeys = [
    GlobalKey<FormState>(),
    GlobalKey<FormState>(),
    GlobalKey<FormState>(),
  ];

  final _titleController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _organizerController = TextEditingController();
  final _locationController = TextEditingController();
  final _registrationController = TextEditingController();
  final _dateController = TextEditingController();
  final _timeController = TextEditingController();
  final _endTimeController = TextEditingController();
  final _itEquipmentController = TextEditingController();
  final _materialsController = TextEditingController();
  final _categoryController = TextEditingController();

  final _scrollController = ScrollController();

  final _titleFocus = FocusNode();
  final _descriptionFocus = FocusNode();
  final _organizerFocus = FocusNode();
  final _locationFocus = FocusNode();
  final _registrationFocus = FocusNode();
  final _itEquipmentFocus = FocusNode();
  final _materialsFocus = FocusNode();

  _SubmitViewMode _viewMode = _SubmitViewMode.form;
  int _currentStep = 0;
  int? _categoryId;
  DateTime? _date;
  TimeOfDay? _time;
  TimeOfDay? _endTime;

  bool _categoriesLoading = true;
  String? _categoriesError;
  List<CategoryModel> _categories = [];
  List<EventModel> _existingEvents = [];

  bool _submitting = false;
  bool _allowPop = false;

  Uint8List? _coverBytes;
  String? _coverFilename;
  String? _coverMime;
  String? _coverRef;
  bool _coverUploading = false;
  bool _coverRemoved = false;
  String? _coverError;

  final _picker = ImagePicker();
  late final String _clientRequestId = createEventRequestId();
  late final String _initialOrganizer;

  @override
  void initState() {
    super.initState();
    _initialOrganizer = AuthStore.firstName ?? '';
    final initial = widget.initialDate;
    if (initial != null) {
      _date = initial;
      _dateController.text = DateFormat('dd.MM.yyyy').format(initial);
    }
    if (widget.initialEvent != null) {
      _prefillFromEvent(widget.initialEvent!);
    } else {
      if (_initialOrganizer.isNotEmpty) {
        _organizerController.text = _initialOrganizer;
      }
    }
    _setupFocusTracking();
    _loadCategories();
    _loadExistingEvents();
  }

  bool get _isResubmit => widget.initialEvent != null;

  bool get _hasUnsavedChanges {
    if (_viewMode == _SubmitViewMode.success) return false;
    if (_coverBytes != null ||
        _coverRef != null ||
        _coverRemoved ||
        _coverUploading) {
      return true;
    }

    final initialEvent = widget.initialEvent;
    if (initialEvent == null) {
      return _titleController.text.isNotEmpty ||
          _descriptionController.text.isNotEmpty ||
          _organizerController.text != _initialOrganizer ||
          _locationController.text.isNotEmpty ||
          _registrationController.text.isNotEmpty ||
          _itEquipmentController.text.isNotEmpty ||
          _materialsController.text.isNotEmpty ||
          !_sameDate(_date, widget.initialDate) ||
          _time != null ||
          _endTime != null ||
          _categoryId != null;
    }

    final categoryChanged =
        _categoryController.text.isNotEmpty &&
        _categoryController.text != initialEvent.category;
    return _titleController.text != initialEvent.title ||
        _descriptionController.text != initialEvent.description ||
        _organizerController.text != initialEvent.organizerName ||
        _locationController.text != initialEvent.location ||
        _registrationController.text != (initialEvent.registrationUrl ?? '') ||
        _itEquipmentController.text != (initialEvent.itEquipment ?? '') ||
        _materialsController.text != (initialEvent.materials ?? '') ||
        _dateKey(_date) != initialEvent.eventDate ||
        _timeKey(_time) != _normalizedTime(initialEvent.eventTime) ||
        _timeKey(_endTime) != _normalizedTime(initialEvent.eventEndTime) ||
        categoryChanged;
  }

  bool get _canPop {
    if (_allowPop || _viewMode == _SubmitViewMode.success) return true;
    if (_submitting || _viewMode != _SubmitViewMode.form) return false;
    return !_hasUnsavedChanges;
  }

  bool _sameDate(DateTime? first, DateTime? second) {
    if (first == null || second == null) return first == second;
    return first.year == second.year &&
        first.month == second.month &&
        first.day == second.day;
  }

  String? _dateKey(DateTime? date) => date == null
      ? null
      : '${date.year.toString().padLeft(4, '0')}-'
            '${date.month.toString().padLeft(2, '0')}-'
            '${date.day.toString().padLeft(2, '0')}';

  String? _timeKey(TimeOfDay? time) => time == null
      ? null
      : '${time.hour.toString().padLeft(2, '0')}:'
            '${time.minute.toString().padLeft(2, '0')}';

  String? _normalizedTime(String? value) {
    if (value == null || value.length < 5) return value;
    return value.substring(0, 5);
  }

  Future<void> _handlePop(bool didPop, bool? result) async {
    if (didPop || !mounted) return;
    if (_submitting) {
      _showMessage(AppLocalizations.get('submissionInProgress'));
      return;
    }
    if (_viewMode != _SubmitViewMode.form) {
      setState(() => _viewMode = _SubmitViewMode.form);
      return;
    }

    final discard = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        title: Text(AppLocalizations.get('unsavedChanges')),
        content: Text(AppLocalizations.get('unsavedChangesMessage')),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AppLocalizations.get('keepEditing')),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(AppLocalizations.get('discard')),
          ),
        ],
      ),
    );
    if (discard != true || !mounted) return;
    setState(() => _allowPop = true);
    Navigator.pop(context, result);
  }

  void _prefillFromEvent(EventModel e) {
    _titleController.text = e.title;
    _descriptionController.text = e.description;
    _organizerController.text = e.organizerName;
    _locationController.text = e.location;
    _registrationController.text = e.registrationUrl ?? '';
    _itEquipmentController.text = e.itEquipment ?? '';
    _materialsController.text = e.materials ?? '';

    final dateParts = e.eventDate.split('-');
    if (dateParts.length == 3) {
      final y = int.tryParse(dateParts[0]);
      final m = int.tryParse(dateParts[1]);
      final d = int.tryParse(dateParts[2]);
      if (y != null && m != null && d != null) {
        _date = DateTime(y, m, d);
        _dateController.text = DateFormat('dd.MM.yyyy').format(_date!);
      }
    }

    final start = _parseTimeOfDay(e.eventTime);
    if (start != null) {
      _time = start;
      _timeController.text = _formatTime(start);
    }
    final end = e.eventEndTime != null
        ? _parseTimeOfDay(e.eventEndTime!)
        : null;
    if (end != null) {
      _endTime = end;
      _endTimeController.text = _formatTime(end);
    }
    // category id is resolved by name once categories load (see _loadCategories)
  }

  TimeOfDay? _parseTimeOfDay(String value) {
    final parts = value.split(':');
    if (parts.length < 2) return null;
    final h = int.tryParse(parts[0]);
    final m = int.tryParse(parts[1]);
    if (h == null || m == null) return null;
    return TimeOfDay(hour: h, minute: m);
  }

  FocusNode? _activeFocus;
  bool get _isEditing {
    if (_activeFocus == null) return false;
    final isMobile =
        Theme.of(context).platform == TargetPlatform.android ||
        Theme.of(context).platform == TargetPlatform.iOS;
    if (!isMobile) return false;
    return MediaQuery.of(context).viewInsets.bottom > 0;
  }

  void _setupFocusTracking() {
    final nodes = [
      _titleFocus,
      _descriptionFocus,
      _organizerFocus,
      _locationFocus,
      _registrationFocus,
      _itEquipmentFocus,
      _materialsFocus,
    ];
    for (var node in nodes) {
      node.addListener(() {
        if (!mounted) return;
        setState(() {
          if (node.hasFocus) {
            _activeFocus = node;
          } else if (_activeFocus == node) {
            _activeFocus = null;
          }
        });

        if (node.hasFocus) {
          Future.delayed(const Duration(milliseconds: 300), () {
            if (!mounted || !node.hasFocus) return;
            final context = node.context;
            if (context != null && context.mounted) {
              Scrollable.ensureVisible(
                context,
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOutCubic,
                alignment:
                    0.5, // Center the active field in the visible area above the keyboard
              );
            }
          });
        }
      });
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    _organizerController.dispose();
    _locationController.dispose();
    _registrationController.dispose();
    _dateController.dispose();
    _timeController.dispose();
    _endTimeController.dispose();
    _itEquipmentController.dispose();
    _materialsController.dispose();
    _categoryController.dispose();
    _scrollController.dispose();
    _titleFocus.dispose();
    _descriptionFocus.dispose();
    _organizerFocus.dispose();
    _locationFocus.dispose();
    _registrationFocus.dispose();
    _itEquipmentFocus.dispose();
    _materialsFocus.dispose();
    super.dispose();
  }

  Future<void> _loadCategories() async {
    setState(() {
      _categoriesLoading = true;
      _categoriesError = null;
    });
    try {
      final categories = await EventCache.instance.categories();
      if (!mounted) return;
      setState(() {
        _categories = categories;
        _categoriesLoading = false;
        if (_categoryId != null) {
          final matched = categories.firstWhere(
            (c) => c.id == _categoryId,
            orElse: () => CategoryModel(id: -1, name: '', slug: ''),
          );
          if (matched.id != -1) {
            _categoryController.text = matched.name;
          }
        } else if (_isResubmit) {
          // resolve the category id from the event's category name
          final name = widget.initialEvent!.category;
          final matched = categories.firstWhere(
            (c) => c.name == name,
            orElse: () => CategoryModel(id: -1, name: '', slug: ''),
          );
          if (matched.id != -1) {
            _categoryId = matched.id;
            _categoryController.text = matched.name;
          }
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _categoriesError = e.toString();
        _categoriesLoading = false;
      });
    }
  }

  Future<void> _loadExistingEvents() async {
    try {
      final approved = await EventCache.instance.approved();
      final pending = await EventCache.instance.pending();
      if (!mounted) return;
      setState(() => _existingEvents = [...approved, ...pending]);
    } catch (_) {
      // Non-fatal
    }
  }

  EventModel? _findConflict() {
    if (_date == null || _time == null || _endTime == null) return null;
    final location = _locationController.text.trim().toLowerCase();
    if (location.isEmpty) return null;

    final newStart = _toMinutes(_time!);
    final newEnd = _toMinutes(_endTime!);
    if (newEnd <= newStart) return null;

    final dateStr = DateFormat('yyyy-MM-dd').format(_date!);

    for (final e in _existingEvents) {
      if (_isResubmit && e.id == widget.initialEvent!.id) continue;
      if (e.eventDate != dateStr) continue;
      if (e.location.trim().toLowerCase() != location) continue;

      final eStart = _parseMinutes(e.eventTime);
      if (eStart == null) continue;
      final eEnd = e.eventEndTime != null
          ? (_parseMinutes(e.eventEndTime!) ?? eStart + 60)
          : eStart + 60;

      if (newStart < eEnd && newEnd > eStart) return e;
    }
    return null;
  }

  int _toMinutes(TimeOfDay t) => t.hour * 60 + t.minute;

  int? _parseMinutes(String time) {
    final parts = time.split(':');
    if (parts.length < 2) return null;
    final h = int.tryParse(parts[0]);
    final m = int.tryParse(parts[1]);
    if (h == null || m == null) return null;
    return h * 60 + m;
  }

  String? _validateTitle(String? value) => validateRequiredEventText(
    value,
    maxLength: EventFormLimits.title,
    emptyMessage: AppLocalizations.get('required'),
    fieldName: 'Title',
  );

  String? _validateDescription(String? value) => validateRequiredEventText(
    value,
    maxLength: EventFormLimits.description,
    emptyMessage: AppLocalizations.get('required'),
    fieldName: 'Description',
    allowLineBreaks: true,
  );

  String? _validateOrganizer(String? value) => validateRequiredEventText(
    value,
    maxLength: EventFormLimits.organizer,
    emptyMessage: AppLocalizations.get('required'),
    fieldName: 'Organizer',
  );

  String? _validateLocation(String? value) => validateRequiredEventText(
    value,
    maxLength: EventFormLimits.location,
    emptyMessage: AppLocalizations.get('required'),
    fieldName: 'Location',
  );

  String? _validateDate(String? value) {
    return validateEventDate(
      _date,
      now: DateTime.now(),
      missingMessage: AppLocalizations.get('specifyDate'),
    );
  }

  String? _validateTime(String? value) {
    return validateEventStartTime(
      date: _date,
      startTime: _time,
      now: DateTime.now(),
      missingMessage: AppLocalizations.get('specifyTime'),
    );
  }

  String? _validateEndTime(String? value) {
    return validateEventEndTime(
      startTime: _time,
      endTime: _endTime,
      missingMessage: AppLocalizations.get('specifyEndTime'),
    );
  }

  String? _validateRegistrationUrl(String? value) {
    return validateEventRegistrationUrl(value);
  }

  bool _isStepValid(int step) {
    if (step == 0) {
      if (_validateDate(_dateController.text) != null) return false;
      if (_validateTime(_timeController.text) != null) return false;
      if (_validateEndTime(_endTimeController.text) != null) return false;
      if (_validateLocation(_locationController.text) != null) return false;
      if (_validateRegistrationUrl(_registrationController.text) != null) {
        return false;
      }
      return true;
    }
    if (step == 1) {
      if (_validateTitle(_titleController.text) != null) return false;
      if (_validateDescription(_descriptionController.text) != null) {
        return false;
      }
      if (_validateOrganizer(_organizerController.text) != null) return false;
      if (_categoryId == null) return false;
      return true;
    }
    // wait for cover upload before submit
    if (step == 2) {
      if (_coverUploading) return false;
      if (validateOptionalEventText(
            _itEquipmentController.text,
            maxLength: EventFormLimits.resource,
            fieldName: 'IT equipment',
            allowLineBreaks: true,
          ) !=
          null) {
        return false;
      }
      if (validateOptionalEventText(
            _materialsController.text,
            maxLength: EventFormLimits.resource,
            fieldName: 'Materials',
            allowLineBreaks: true,
          ) !=
          null) {
        return false;
      }
      return true;
    }
    return true;
  }

  void _onPrimary() {
    final valid = _formKeys[_currentStep].currentState?.validate() ?? false;
    if (!valid) return;

    if (_currentStep == 0) {
      final conflict = _findConflict();
      if (conflict != null) {
        _showConflictDialog(conflict);
        return;
      }
    }

    if (_currentStep < 2) {
      setState(() => _currentStep++);
    } else {
      _submit();
    }
  }

  void _showConflictDialog(EventModel conflict) {
    final timeRange = conflict.eventEndTime != null
        ? '${conflict.eventTime} – ${conflict.eventEndTime}'
        : conflict.eventTime;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const AppIcon(AppIcons.warning, color: AppColors.warning),
        title: const Text('Time conflict'),
        content: Text(
          '"${conflict.title}" is already booked at ${conflict.location} '
          'on this date ($timeRange). '
          'Please choose a different time or location.',
        ),
        actions: [
          AppTextButton(text: 'OK', onPressed: () => Navigator.pop(ctx)),
        ],
      ),
    );
  }

  void _pickDate() {
    FocusScope.of(context).unfocus();
    setState(() => _viewMode = _SubmitViewMode.datePicker);
  }

  void _pickTime() {
    FocusScope.of(context).unfocus();
    setState(() => _viewMode = _SubmitViewMode.timePicker);
  }

  void _pickEndTime() {
    FocusScope.of(context).unfocus();
    setState(() => _viewMode = _SubmitViewMode.endTimePicker);
  }

  void _pickCategory() {
    FocusScope.of(context).unfocus();
    setState(() => _viewMode = _SubmitViewMode.categoryPicker);
  }

  String _formatTime(TimeOfDay t) {
    final h = t.hour.toString().padLeft(2, '0');
    final m = t.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  Future<void> _submit() async {
    // Guard against a double-tap racing a submit already in flight: a second tap
    // must never fire a second create/resubmit (which would produce a duplicate
    // pending event). The step-validity check does not cover _submitting, so
    // this is the authoritative guard.
    if (_submitting) return;
    if (_coverUploading) {
      _showMessage(AppLocalizations.get('coverStillUploading'));
      return;
    }
    int? invalidStep;
    for (var step = 0; step < _formKeys.length; step++) {
      if (!_isStepValid(step)) {
        invalidStep = step;
        break;
      }
    }
    if (invalidStep != null) {
      final stepToReview = invalidStep;
      setState(() => _currentStep = stepToReview);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _formKeys[stepToReview].currentState?.validate();
      });
      _showMessage('Please review the highlighted fields');
      return;
    }
    setState(() => _submitting = true);
    try {
      final fields = {
        'title': _titleController.text.trim(),
        'description': _descriptionController.text.trim(),
        'event_date': DateFormat('yyyy-MM-dd').format(_date!),
        'event_time': _formatTime(_time!),
        'event_end_time': _formatTime(_endTime!),
        'location': _locationController.text.trim(),
        'category_id': _categoryId,
        'organizer_name': _organizerController.text.trim(),
        'it_equipment': _nullIfEmpty(_itEquipmentController.text),
        'materials': _nullIfEmpty(_materialsController.text),
        'registration_url': _nullIfEmpty(_registrationController.text),
      };
      fields['client_request_id'] = _clientRequestId;
      if (_coverRef != null) {
        fields['cover_ref'] = _coverRef;
      }
      if (_isResubmit && _coverRemoved) {
        fields['remove_cover'] = true;
      }
      if (_isResubmit) {
        await EventCache.instance.resubmit(widget.initialEvent!.id, fields);
      } else {
        await EventCache.instance.submit(fields);
      }
      if (!mounted) return;
      setState(() => _viewMode = _SubmitViewMode.success);
    } on ConflictException catch (e) {
      _showMessage(e.message);
    } on ApiException catch (e) {
      _showMessage(e.message);
    } catch (_) {
      _showMessage(AppLocalizations.get('somethingWentWrong'));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String? _nullIfEmpty(String value) =>
      value.trim().isEmpty ? null : value.trim();

  Widget _buildSuccessView({Key? key}) {
    return KeyedSubtree(
      key: key,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: AppSpacing.screenPadding.copyWith(
            top: AppSpacing.xs,
            bottom: AppSpacing.lg,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const AppIcon(
                AppIcons.checkCircle,
                color: AppColors.success,
                size: 64,
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                AppLocalizations.get('moderationTimeframe'),
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.grey, fontSize: 14),
              ),
              const SizedBox(height: AppSpacing.xl),
              AppPrimaryButton(
                size: AppButtonSize.medium,
                text: 'Yay!',
                onPressed: () => Navigator.pop(context, true),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(SnackBar(content: Text(message)));
  }

  String get _currentTitle {
    switch (_viewMode) {
      case _SubmitViewMode.form:
        return AppLocalizations.get(_isResubmit ? 'editEvent' : 'newEvent');
      case _SubmitViewMode.datePicker:
        return AppLocalizations.get('date');
      case _SubmitViewMode.timePicker:
        return AppLocalizations.get('time');
      case _SubmitViewMode.endTimePicker:
        return AppLocalizations.get('endTime');
      case _SubmitViewMode.categoryPicker:
        return AppLocalizations.get('category');
      case _SubmitViewMode.success:
        return AppLocalizations.get('sent');
    }
  }

  @override
  Widget build(BuildContext context) {
    late final Widget content;
    if (widget.asSheet) {
      content = Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
          child: Material(
            color: Theme.of(context).scaffoldBackgroundColor,
            child: SafeArea(
              top: false,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: AppSpacing.sm),
                  Container(
                    width: 36,
                    height: 4,
                    decoration: BoxDecoration(
                      color: AppColors.grey.withValues(alpha: 0.35),
                      borderRadius: BorderRadius.circular(999),
                    ),
                  ),
                  _buildFocusAnim(
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      child: Center(
                        child: Text(
                          _currentTitle,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                    !_isEditing,
                  ),
                  Flexible(child: _buildBodyContainer()),
                ],
              ),
            ),
          ),
        ),
      );
    } else {
      content = Scaffold(
        appBar: AppAppBar(showBackButton: true, title: _currentTitle),
        body: _buildBodyContainer(),
      );
    }

    return PopScope<bool>(
      canPop: _canPop,
      onPopInvokedWithResult: _handlePop,
      child: content,
    );
  }

  Widget _buildBodyContainer() {
    if (_categoriesLoading) {
      return const SizedBox(height: 380, child: Center(child: AppLoader()));
    }
    if (_categoriesError != null) {
      return Center(
        child: Padding(
          padding: AppSpacing.screenPadding,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_categoriesError!, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.df),
              AppSecondaryButton(
                size: AppButtonSize.medium,
                text: AppLocalizations.get('retry'),
                onPressed: _loadCategories,
              ),
            ],
          ),
        ),
      );
    }

    return AnimatedSize(
      duration: const Duration(milliseconds: 400),
      curve: Curves.fastOutSlowIn,
      alignment: Alignment.topCenter,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 400),
        switchInCurve: Curves.fastOutSlowIn,
        switchOutCurve: Curves.fastOutSlowIn,
        layoutBuilder: (currentChild, previousChildren) {
          return Stack(
            alignment: Alignment.topCenter,
            children: <Widget>[
              ...previousChildren.map(
                (child) => Positioned(top: 0, left: 0, right: 0, child: child),
              ),
              ?currentChild,
            ],
          );
        },
        transitionBuilder: (child, animation) {
          // Fade-through pattern prevents seeing both states at once.
          return FadeTransition(
            opacity: CurvedAnimation(
              parent: animation,
              curve: const Interval(0.5, 1.0, curve: Curves.easeIn),
            ),
            child: ScaleTransition(
              scale: Tween<double>(begin: 0.95, end: 1.0).animate(
                CurvedAnimation(
                  parent: animation,
                  curve: const Interval(0.5, 1.0, curve: Curves.easeOutCubic),
                ),
              ),
              child: child,
            ),
          );
        },
        child: _buildCurrentView(),
      ),
    );
  }

  Widget _buildCurrentView() {
    switch (_viewMode) {
      case _SubmitViewMode.form:
        return _buildFormView(key: const ValueKey('form'));
      case _SubmitViewMode.datePicker:
        return _buildDatePickerView(key: const ValueKey('date'));
      case _SubmitViewMode.timePicker:
        return _buildTimePickerView(key: const ValueKey('time'), isEnd: false);
      case _SubmitViewMode.endTimePicker:
        return _buildTimePickerView(
          key: const ValueKey('endTime'),
          isEnd: true,
        );
      case _SubmitViewMode.categoryPicker:
        return _buildCategoryPickerView(key: const ValueKey('categoryPicker'));
      case _SubmitViewMode.success:
        return _buildSuccessView(key: const ValueKey('success'));
    }
  }

  Widget _buildDatePickerView({Key? key}) {
    final now = DateUtils.dateOnly(DateTime.now());
    final defaultLastDate = now.add(const Duration(days: 365));
    final selectedDate = DateUtils.dateOnly(_date ?? now);
    final lastDate = selectedDate.isAfter(defaultLastDate)
        ? selectedDate
        : defaultLastDate;
    final pickerDate = clampEventPickerDate(
      _date ?? now,
      firstDate: now,
      lastDate: lastDate,
    );
    final isLight = Theme.of(context).brightness == Brightness.light;
    final textPrimary = isLight ? const Color(0xFF0A0A1A) : Colors.white;
    final textSub = isLight ? const Color(0xFF6B6B80) : const Color(0xFF8E8EA3);
    return KeyedSubtree(
      key: key,
      child: Padding(
        padding: AppSpacing.screenPadding,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Theme(
              data: Theme.of(context).copyWith(
                colorScheme: Theme.of(context).colorScheme.copyWith(
                  primary: AppColors.primary,
                  onPrimary: Colors.white,
                  onSurface: textPrimary,
                  onSurfaceVariant: textSub,
                ),
              ),
              child: CalendarDatePicker(
                initialDate: pickerDate,
                firstDate: now,
                lastDate: lastDate,
                onDateChanged: (date) {
                  setState(() {
                    _date = date;
                    _dateController.text = DateFormat(
                      'dd.MM.yyyy',
                    ).format(date);
                    _viewMode = _SubmitViewMode.form;
                  });
                },
              ),
            ),
            const SizedBox(height: AppSpacing.df),
            AppPrimaryButton(
              size: AppButtonSize.medium,
              text: 'OK',
              onPressed: () {
                setState(() {
                  _date = pickerDate;
                  _dateController.text = DateFormat(
                    'dd.MM.yyyy',
                  ).format(_date!);
                  _viewMode = _SubmitViewMode.form;
                });
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTimePickerView({Key? key, required bool isEnd}) {
    final startMinutes = _time == null ? null : _toMinutes(_time!);
    final defaultEndMinutes = min((startMinutes ?? 14 * 60) + 60, 23 * 60 + 59);
    final defaultHour = isEnd ? defaultEndMinutes ~/ 60 : 15;
    final defaultMinute = isEnd ? defaultEndMinutes % 60 : 0;

    return KeyedSubtree(
      key: key,
      child: Padding(
        padding: AppSpacing.screenPadding,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: 120,
              child: Transform.scale(
                scaleX: 1.15,
                child: CupertinoDatePicker(
                  mode: CupertinoDatePickerMode.time,
                  use24hFormat: true,
                  initialDateTime: DateTime(
                    0,
                    0,
                    0,
                    (isEnd ? _endTime : _time)?.hour ?? defaultHour,
                    (isEnd ? _endTime : _time)?.minute ?? defaultMinute,
                  ),
                  onDateTimeChanged: (DateTime newDateTime) {
                    setState(() {
                      final t = TimeOfDay(
                        hour: newDateTime.hour,
                        minute: newDateTime.minute,
                      );
                      if (isEnd) {
                        _endTime = t;
                        _endTimeController.text = _formatTime(t);
                      } else {
                        _time = t;
                        _timeController.text = _formatTime(t);
                        if (_endTime != null) {
                          if (_toMinutes(_endTime!) <= _toMinutes(_time!)) {
                            _endTime = null;
                            _endTimeController.clear();
                          }
                        }
                      }
                    });
                  },
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            AppPrimaryButton(
              size: AppButtonSize.medium,
              text: 'OK',
              onPressed: () {
                setState(() {
                  if (isEnd) {
                    if (_endTime == null) {
                      final t = TimeOfDay(
                        hour: defaultHour,
                        minute: defaultMinute,
                      );
                      _endTime = t;
                      _endTimeController.text = _formatTime(t);
                    }
                  } else {
                    if (_time == null) {
                      final t = TimeOfDay(
                        hour: defaultHour,
                        minute: defaultMinute,
                      );
                      _time = t;
                      _timeController.text = _formatTime(t);
                    }
                  }
                  _viewMode = _SubmitViewMode.form;
                });
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCategoryPickerView({Key? key}) {
    final theme = Theme.of(context);
    final isLight = theme.brightness == Brightness.light;
    return KeyedSubtree(
      key: key,
      child: Padding(
        padding: AppSpacing.screenPadding,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_categoriesLoading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.lg),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (_categoriesError != null)
              Center(
                child: Text(
                  _categoriesError!,
                  style: const TextStyle(color: AppColors.error),
                ),
              )
            else
              Align(
                alignment: Alignment.center,
                child: Wrap(
                  spacing: AppSpacing.sm,
                  runSpacing: AppSpacing.sm,
                  alignment: WrapAlignment.center,
                  children: [
                    for (final category in _categories)
                      ChoiceChip(
                        label: Text(category.name),
                        selected: _categoryId == category.id,
                        onSelected: (selected) {
                          if (selected) {
                            setState(() {
                              _categoryId = category.id;
                              _categoryController.text = category.name;
                              _viewMode = _SubmitViewMode.form;
                            });
                          }
                        },
                        selectedColor: AppColors.primary.withValues(
                          alpha: 0.15,
                        ),
                        checkmarkColor: AppColors.primary,
                        backgroundColor: isLight
                            ? AppColors.fieldBackground
                            : AppColors.surfaceDark,
                        labelStyle: TextStyle(
                          color: _categoryId == category.id
                              ? AppColors.primary
                              : (isLight
                                    ? AppColors.textPrimary
                                    : AppColors.textPrimaryDark),
                          fontWeight: _categoryId == category.id
                              ? FontWeight.bold
                              : FontWeight.normal,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8.0),
                          side: BorderSide(
                            color: _categoryId == category.id
                                ? AppColors.primary
                                : Colors.transparent,
                            width: 1,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            const SizedBox(height: AppSpacing.lg),
            AppPrimaryButton(
              size: AppButtonSize.medium,
              text: 'OK',
              onPressed: () => setState(() => _viewMode = _SubmitViewMode.form),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFormView({Key? key}) {
    return KeyedSubtree(
      key: key,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildProgress(),
          Flexible(
            child: SingleChildScrollView(
              controller: _scrollController,
              padding: AppSpacing.screenPadding,
              child: _buildStep(),
            ),
          ),
          _buildBottomBar(),
        ],
      ),
    );
  }

  Widget _buildProgress() {
    final theme = Theme.of(context);
    final labels = [
      AppLocalizations.get('dateTimeTab'),
      AppLocalizations.get('basicTab'),
      AppLocalizations.get('resourcesTab'),
    ];
    return _buildFocusAnim(
      Column(
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOutCubic,
            height: 4,
            margin: const EdgeInsets.symmetric(horizontal: AppSpacing.df),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              color: AppColors.fieldBackground,
            ),
            child: Row(
              children: [
                Expanded(
                  flex: _currentStep + 1,
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(999),
                      color: AppColors.primary,
                    ),
                  ),
                ),
                Expanded(flex: 2 - _currentStep, child: const SizedBox()),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.df,
              vertical: AppSpacing.sm,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                for (var i = 0; i < labels.length; i++)
                  AnimatedDefaultTextStyle(
                    duration: const Duration(milliseconds: 200),
                    style: theme.textTheme.bodySmall!.copyWith(
                      color: i == _currentStep
                          ? AppColors.primary
                          : AppColors.grey,
                      fontWeight: i == _currentStep
                          ? FontWeight.bold
                          : FontWeight.normal,
                    ),
                    child: Text(labels[i]),
                  ),
              ],
            ),
          ),
        ],
      ),
      !_isEditing,
    );
  }

  Widget _buildStep() {
    switch (_currentStep) {
      case 0:
        return _stepPlaceTime();
      case 1:
        return _stepBasic();
      default:
        return _stepResources();
    }
  }

  Widget _stepBasic() {
    return Form(
      key: _formKeys[1],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildFocusAnim(
            AppTextField(
              controller: _titleController,
              focusNode: _titleFocus,
              label: AppLocalizations.get('title'),
              maxLength: EventFormLimits.title,
              validator: _validateTitle,
              textCapitalization: TextCapitalization.sentences,
            ),
            !_isEditing || _titleFocus.hasFocus,
            focusNode: _titleFocus,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _descriptionController,
              focusNode: _descriptionFocus,
              label: AppLocalizations.get('description'),
              maxLines: 4,
              maxLength: EventFormLimits.description,
              validator: _validateDescription,
              textCapitalization: TextCapitalization.sentences,
            ),
            !_isEditing || _descriptionFocus.hasFocus,
            focusNode: _descriptionFocus,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _organizerController,
              focusNode: _organizerFocus,
              label: AppLocalizations.get('organizer'),
              maxLength: EventFormLimits.organizer,
              validator: _validateOrganizer,
              textCapitalization: TextCapitalization.words,
            ),
            !_isEditing || _organizerFocus.hasFocus,
            focusNode: _organizerFocus,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _categoryController,
              label: AppLocalizations.get('category'),
              readOnly: true,
              onTap: _pickCategory,
              validator: (_) => _categoryId == null
                  ? AppLocalizations.get('selectCategory')
                  : null,
            ),
            !_isEditing,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(_buildCoverSection(), !_isEditing),
        ],
      ),
    );
  }

  bool get _hasExistingCover =>
      _isResubmit &&
      widget.initialEvent!.coverUrl != null &&
      !_coverRemoved &&
      _coverBytes == null;

  bool get _hasCover => _coverBytes != null || _hasExistingCover;

  Widget _buildCoverSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AnimatedSize(
          duration: const Duration(milliseconds: 300),
          curve: Curves.fastOutSlowIn,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.md),
            child: AspectRatio(
              aspectRatio: 16 / 9,
              child: _hasCover
                  ? _buildCoverPreview()
                  : _buildCoverPlaceholder(),
            ),
          ),
        ),
        if (_coverError != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(
            _coverError!,
            style: const TextStyle(color: AppColors.error, fontSize: 13),
          ),
        ],
        const SizedBox(height: AppSpacing.sm),
        _buildCoverActions(),
      ],
    );
  }

  Widget _buildCoverPreview() {
    final Widget image = _coverBytes != null
        ? Image.memory(_coverBytes!, fit: BoxFit.cover)
        : Image.network(
            widget.initialEvent!.coverUrl!,
            fit: BoxFit.cover,
            errorBuilder: (_, _, _) => _buildCoverPlaceholder(),
          );
    return Stack(
      fit: StackFit.expand,
      children: [
        GestureDetector(
          onTap: _coverUploading ? null : _showCoverFullscreen,
          child: image,
        ),
        if (_coverUploading)
          Container(
            color: Colors.black.withValues(alpha: 0.45),
            alignment: Alignment.center,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const AppLoader(),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  AppLocalizations.get('uploading'),
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildCoverPlaceholder() {
    final isLight = Theme.of(context).brightness == Brightness.light;
    return GestureDetector(
      onTap: _coverUploading ? null : _startPickCover,
      child: Container(
        color: isLight ? AppColors.fieldBackground : AppColors.surfaceDark,
        alignment: Alignment.center,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const AppIcon(AppIcons.image, color: AppColors.grey, size: 40),
            const SizedBox(height: AppSpacing.sm),
            Text(
              AppLocalizations.get('addCover'),
              style: const TextStyle(color: AppColors.grey, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCoverActions() {
    if (!_hasCover) {
      if (_coverError != null) {
        return Row(
          children: [
            Expanded(
              child: AppSecondaryButton(
                size: AppButtonSize.small,
                text: AppLocalizations.get('addCover'),
                onPressed: _coverUploading ? null : _startPickCover,
              ),
            ),
          ],
        );
      }
      return const SizedBox.shrink();
    }
    return Row(
      children: [
        Expanded(
          child: AppSecondaryButton(
            size: AppButtonSize.small,
            text: _coverError != null
                ? AppLocalizations.get('retry')
                : AppLocalizations.get('replace'),
            onPressed: _coverUploading
                ? null
                : (_coverError != null
                      ? _uploadCurrentCover
                      : _confirmReplaceCover),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: AppSecondaryButton(
            size: AppButtonSize.small,
            text: AppLocalizations.get('remove'),
            onPressed: _coverUploading ? null : _confirmRemoveCover,
          ),
        ),
      ],
    );
  }

  ({String filename, String mime})? _sniffImage(Uint8List b) {
    if (b.length >= 3 && b[0] == 0xFF && b[1] == 0xD8 && b[2] == 0xFF) {
      return (filename: 'cover.jpg', mime: 'image/jpeg');
    }
    if (b.length >= 8 &&
        b[0] == 0x89 &&
        b[1] == 0x50 &&
        b[2] == 0x4E &&
        b[3] == 0x47) {
      return (filename: 'cover.png', mime: 'image/png');
    }
    if (b.length >= 12 &&
        b[0] == 0x52 &&
        b[1] == 0x49 &&
        b[2] == 0x46 &&
        b[3] == 0x46 &&
        b[8] == 0x57 &&
        b[9] == 0x45 &&
        b[10] == 0x42 &&
        b[11] == 0x50) {
      return (filename: 'cover.webp', mime: 'image/webp');
    }
    if (b.length >= 6 && b[0] == 0x47 && b[1] == 0x49 && b[2] == 0x46) {
      return (filename: 'cover.gif', mime: 'image/gif');
    }
    return null;
  }

  Future<void> _startPickCover() async {
    final source = await _chooseImageSource();
    if (source == null) return;
    XFile? picked;
    try {
      picked = await _picker.pickImage(
        source: source,
        maxWidth: 2560,
        maxHeight: 2560,
        imageQuality: 90,
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _coverError = AppLocalizations.get('coverPickFailed'));
      return;
    }
    if (picked == null) return;
    final bytes = await picked.readAsBytes();
    final sniff = _sniffImage(bytes);
    if (sniff == null) {
      if (!mounted) return;
      setState(() {
        _coverError = AppLocalizations.get('coverUnsupported');
      });
      return;
    }
    if (!mounted) return;
    setState(() {
      _coverBytes = bytes;
      _coverFilename = sniff.filename;
      _coverMime = sniff.mime;
      _coverRef = null;
      _coverRemoved = false;
      _coverError = null;
    });
    await _uploadCurrentCover();
  }

  Future<void> _uploadCurrentCover() async {
    final bytes = _coverBytes;
    if (bytes == null) return;
    setState(() {
      _coverUploading = true;
      _coverError = null;
    });
    try {
      final ref = await uploadCover(
        bytes: bytes,
        filename: _coverFilename ?? 'cover.jpg',
        contentType: _coverMime,
      );
      if (!mounted) return;
      setState(() {
        _coverRef = ref;
        _coverUploading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _coverUploading = false;
        _coverRef = null;
        _coverError = e.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _coverUploading = false;
        _coverRef = null;
        _coverError = AppLocalizations.get('coverUploadFailed');
      });
    }
  }

  Future<ImageSource?> _chooseImageSource() {
    return showModalBottomSheet<ImageSource>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const AppIcon(AppIcons.image),
              title: Text(AppLocalizations.get('gallery')),
              onTap: () => Navigator.pop(ctx, ImageSource.gallery),
            ),
            ListTile(
              leading: const AppIcon(AppIcons.camera),
              title: Text(AppLocalizations.get('camera')),
              onTap: () => Navigator.pop(ctx, ImageSource.camera),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmReplaceCover() async {
    await _startPickCover();
  }

  Future<void> _confirmRemoveCover() async {
    if (!mounted) return;
    setState(() {
      _coverBytes = null;
      _coverFilename = null;
      _coverMime = null;
      _coverRef = null;
      _coverError = null;
      _coverRemoved = true;
    });
  }

  void _showCoverFullscreen() {
    final Widget image = _coverBytes != null
        ? Image.memory(_coverBytes!, fit: BoxFit.contain)
        : Image.network(widget.initialEvent!.coverUrl!, fit: BoxFit.contain);
    showDialog<void>(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.9),
      builder: (ctx) => GestureDetector(
        onTap: () => Navigator.pop(ctx),
        child: Center(
          child: InteractiveViewer(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: image,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFocusAnim(Widget child, bool isVisible, {FocusNode? focusNode}) {
    final showDone = _isEditing && focusNode != null && focusNode.hasFocus;

    final content = focusNode != null
        ? Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(child: child),
              AnimatedSize(
                duration: const Duration(milliseconds: 250),
                curve: Curves.fastOutSlowIn,
                child: showDone
                    ? Padding(
                        padding: const EdgeInsets.only(left: AppSpacing.sm),
                        child: AppTextButton(
                          text: AppLocalizations.get('done'),
                          onPressed: () {
                            focusNode.unfocus();
                          },
                        ),
                      )
                    : const SizedBox(width: 0),
              ),
            ],
          )
        : child;

    return AnimatedSize(
      duration: const Duration(milliseconds: 350),
      curve: Curves.fastOutSlowIn,
      alignment: Alignment.topCenter,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 250),
        layoutBuilder: (currentChild, previousChildren) {
          return Stack(
            alignment: Alignment.topCenter,
            children: <Widget>[
              ...previousChildren.map(
                (c) => Positioned(top: 0, left: 0, right: 0, child: c),
              ),
              ?currentChild,
            ],
          );
        },
        child: isVisible
            ? content
            : const SizedBox(
                key: ValueKey('hidden'),
                width: double.infinity,
                height: 0,
              ),
      ),
    );
  }

  Widget _stepPlaceTime() {
    return Form(
      key: _formKeys[0],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildFocusAnim(
            AppTextField(
              controller: _dateController,
              label: AppLocalizations.get('date'),
              readOnly: true,
              onTap: _pickDate,
              validator: _validateDate,
            ),
            !_isEditing,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _timeController,
              label: AppLocalizations.get('time'),
              readOnly: true,
              onTap: _pickTime,
              validator: _validateTime,
            ),
            !_isEditing,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _endTimeController,
              label: AppLocalizations.get('endTime'),
              readOnly: true,
              onTap: _pickEndTime,
              validator: _validateEndTime,
            ),
            !_isEditing,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _locationController,
              focusNode: _locationFocus,
              label: AppLocalizations.get('place'),
              maxLength: EventFormLimits.location,
              validator: _validateLocation,
              textCapitalization: TextCapitalization.words,
            ),
            !_isEditing || _locationFocus.hasFocus,
            focusNode: _locationFocus,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _registrationController,
              focusNode: _registrationFocus,
              label: AppLocalizations.get('registrationUrl'),
              keyboardType: TextInputType.url,
              maxLength: EventFormLimits.registrationUrl,
              errorText: _validateRegistrationUrl(_registrationController.text),
              onChanged: (_) => setState(() {}),
              validator: _validateRegistrationUrl,
            ),
            !_isEditing || _registrationFocus.hasFocus,
            focusNode: _registrationFocus,
          ),
        ],
      ),
    );
  }

  Widget _stepResources() {
    return Form(
      key: _formKeys[2],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildFocusAnim(
            AppTextField(
              controller: _itEquipmentController,
              focusNode: _itEquipmentFocus,
              label: AppLocalizations.get('itEquipment'),
              hint: AppLocalizations.get('itEquipmentHint'),
              maxLines: 3,
              maxLength: EventFormLimits.resource,
              validator: (value) => validateOptionalEventText(
                value,
                maxLength: EventFormLimits.resource,
                fieldName: 'IT equipment',
                allowLineBreaks: true,
              ),
              textCapitalization: TextCapitalization.sentences,
            ),
            !_isEditing || _itEquipmentFocus.hasFocus,
            focusNode: _itEquipmentFocus,
          ),
          _buildFocusAnim(const SizedBox(height: AppSpacing.df), !_isEditing),
          _buildFocusAnim(
            AppTextField(
              controller: _materialsController,
              focusNode: _materialsFocus,
              label: AppLocalizations.get('materials'),
              hint: AppLocalizations.get('materialsHint'),
              maxLines: 3,
              maxLength: EventFormLimits.resource,
              validator: (value) => validateOptionalEventText(
                value,
                maxLength: EventFormLimits.resource,
                fieldName: 'Materials',
                allowLineBreaks: true,
              ),
              textCapitalization: TextCapitalization.sentences,
            ),
            !_isEditing || _materialsFocus.hasFocus,
            focusNode: _materialsFocus,
          ),
        ],
      ),
    );
  }

  Widget _buildBottomBar() {
    return _buildFocusAnim(
      SafeArea(
        top: false,
        child: AnimatedBuilder(
          animation: Listenable.merge([
            _locationController,
            _registrationController,
            _titleController,
            _descriptionController,
            _organizerController,
            _itEquipmentController,
            _materialsController,
          ]),
          builder: (context, child) {
            final isValid = _isStepValid(_currentStep);
            return Padding(
              padding: AppSpacing.screenPadding,
              child: Row(
                children: [
                  if (_currentStep > 0) ...[
                    Expanded(
                      child: AppSecondaryButton(
                        size: AppButtonSize.medium,
                        text: AppLocalizations.get('back'),
                        onPressed: _submitting
                            ? null
                            : () => setState(() => _currentStep--),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                  ],
                  Expanded(
                    child: AppPrimaryButton(
                      size: AppButtonSize.medium,
                      text: _currentStep < 2
                          ? AppLocalizations.get('next')
                          : AppLocalizations.get('sendRequest'),
                      isLoading: _submitting,
                      onPressed: isValid ? _onPrimary : null,
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
      !_isEditing,
    );
  }
}
