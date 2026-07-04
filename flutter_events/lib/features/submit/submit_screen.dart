import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../core/exceptions.dart';
import '../../core/localization.dart';
import '../../models/category_model.dart';
import '../../models/event_model.dart';

class SubmitScreen extends StatefulWidget {
  const SubmitScreen({super.key, this.initialDate, this.asSheet = false});

  /// Optionally pre-fills the event date, e.g. when opened from the shared
  /// calendar for a specific day.
  final DateTime? initialDate;
  final bool asSheet;

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

  @override
  void initState() {
    super.initState();
    final initial = widget.initialDate;
    if (initial != null) {
      _date = initial;
      _dateController.text = DateFormat('dd.MM.yyyy').format(initial);
    }
    _loadCategories();
    _loadExistingEvents();
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
    super.dispose();
  }

  Future<void> _loadCategories() async {
    setState(() {
      _categoriesLoading = true;
      _categoriesError = null;
    });
    try {
      final categories = await fetchCategories();
      if (!mounted) return;
      setState(() {
        _categories = categories;
        _categoriesLoading = false;
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
      final approved = await fetchApprovedEvents();
      final pending = await fetchPendingEvents();
      if (!mounted) return;
      setState(() => _existingEvents = [...approved, ...pending]);
    } catch (_) {
      // Non-fatal — server will still catch conflicts on submit.
    }
  }

  // Returns the conflicting event if the chosen date/time/location overlap
  // with any existing approved or pending event at the same location.
  EventModel? _findConflict() {
    if (_date == null || _time == null || _endTime == null) return null;
    final location = _locationController.text.trim().toLowerCase();
    if (location.isEmpty) return null;

    final newStart = _toMinutes(_time!);
    final newEnd = _toMinutes(_endTime!);
    if (newEnd <= newStart) return null;

    final dateStr = DateFormat('yyyy-MM-dd').format(_date!);

    for (final e in _existingEvents) {
      if (e.eventDate != dateStr) continue;
      if (e.location.trim().toLowerCase() != location) continue;

      final eStart = _parseMinutes(e.eventTime);
      if (eStart == null) continue;
      final eEnd = e.eventEndTime != null
          ? (_parseMinutes(e.eventEndTime!) ?? eStart + 60)
          : eStart + 60;

      // Overlap: new starts before existing ends AND new ends after existing starts.
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

  String? _required(String? value) {
    if (value == null || value.trim().isEmpty) {
      return AppLocalizations.get('required');
    }
    return null;
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
        icon: const Icon(Icons.warning_amber_rounded, color: AppColors.warning),
        title: const Text('Time conflict'),
        content: Text(
          '"${conflict.title}" is already booked at ${conflict.location} '
          'on this date ($timeRange). '
          'Please choose a different time or location.',
        ),
        actions: [
          AppTextButton(
            text: 'OK',
            onPressed: () => Navigator.pop(ctx),
          ),
        ],
      ),
    );
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? now,
      firstDate: now,
      lastDate: now.add(const Duration(days: 365)),
    );
    if (picked == null) return;
    setState(() {
      _date = picked;
      _dateController.text = DateFormat('dd.MM.yyyy').format(picked);
    });
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: _time ?? TimeOfDay.now(),
    );
    if (picked == null) return;
    setState(() {
      _time = picked;
      _timeController.text = _formatTime(picked);
    });
  }

  Future<void> _pickEndTime() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: _endTime ?? TimeOfDay.now(),
    );
    if (picked == null) return;
    setState(() {
      _endTime = picked;
      _endTimeController.text = _formatTime(picked);
    });
  }

  String _formatTime(TimeOfDay t) {
    final h = t.hour.toString().padLeft(2, '0');
    final m = t.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  Future<void> _submit() async {
    setState(() => _submitting = true);
    try {
      final event = await submitEvent({
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
      });
      if (!mounted) return;
      await _showSuccess(event.id);
    } on ConflictException catch (e) {
      _showMessage(e.message);
    } on ApiException catch (e) {
      _showMessage(e.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String? _nullIfEmpty(String value) =>
      value.trim().isEmpty ? null : value.trim();

  Future<void> _showSuccess(int eventId) {
    return showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return AlertDialog(
          icon: const Icon(Icons.check_circle, color: AppColors.success),
          title: Text(AppLocalizations.get('sent')),
          content: Text(
            AppLocalizations.get('moderationTimeframe'),
          ),
          actions: [
            AppTextButton(
              text: AppLocalizations.get('toEvents'),
              onPressed: () {
                Navigator.pop(dialogContext);
                Navigator.pop(context, true);
              },
            ),
          ],
        );
      },
    );
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    if (widget.asSheet) {
      return ClipRRect(
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
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  child: Center(
                    child: Text(
                      AppLocalizations.get('newEvent'),
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
                Flexible(child: _buildBody()),
              ],
            ),
          ),
        ),
      );
    }
    return Scaffold(
      appBar: AppAppBar(
        showBackButton: true,
        title: AppLocalizations.get('newEvent'),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_categoriesLoading) {
      return const SizedBox(
        height: 380,
        child: Center(child: AppLoader()),
      );
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
                text: AppLocalizations.get('retry'),
                onPressed: _loadCategories,
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildProgress(),
        Flexible(
          child: SingleChildScrollView(
            padding: AppSpacing.screenPadding,
            child: _buildStep(),
          ),
        ),
        _buildBottomBar(),
      ],
    );
  }

  Widget _buildProgress() {
    final theme = Theme.of(context);
    final labels = [
      AppLocalizations.get('dateTimeTab'),
      AppLocalizations.get('basicTab'),
      AppLocalizations.get('resourcesTab'),
    ];
    return Column(
      children: [
        LinearProgressIndicator(
          value: (_currentStep + 1) / 3,
          color: AppColors.primary,
          backgroundColor: AppColors.fieldBackground,
          minHeight: 4,
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
                Text(
                  labels[i],
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: i == _currentStep
                        ? AppColors.primary
                        : AppColors.grey,
                  ),
                ),
            ],
          ),
        ),
      ],
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
          AppTextField(
            controller: _titleController,
            label: AppLocalizations.get('title'),
            validator: _required,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _descriptionController,
            label: AppLocalizations.get('description'),
            maxLines: 4,
            validator: _required,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _organizerController,
            label: AppLocalizations.get('organizer'),
            validator: _required,
          ),
          const SizedBox(height: AppSpacing.df),
          _categoryDropdown(),
        ],
      ),
    );
  }

  Widget _categoryDropdown() {
    return DropdownButtonFormField<int>(
      initialValue: _categoryId,
      isExpanded: true,
      borderRadius: AppSpacing.borderRadiusMd,
      decoration: InputDecoration(
        labelText: AppLocalizations.get('category'),
      ),
      items: [
        for (final category in _categories)
          DropdownMenuItem(value: category.id, child: Text(category.name)),
      ],
      onChanged: (value) => setState(() => _categoryId = value),
      validator: (value) =>
          value == null ? AppLocalizations.get('selectCategory') : null,
    );
  }

  Widget _stepPlaceTime() {
    return Form(
      key: _formKeys[0],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppTextField(
            controller: _dateController,
            label: AppLocalizations.get('date'),
            readOnly: true,
            onTap: _pickDate,
            suffixIcon: const Icon(Icons.calendar_today_outlined),
            validator: (_) =>
                _date == null ? AppLocalizations.get('specifyDate') : null,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _timeController,
            label: AppLocalizations.get('time'),
            readOnly: true,
            onTap: _pickTime,
            suffixIcon: const Icon(Icons.access_time_outlined),
            validator: (_) =>
                _time == null ? AppLocalizations.get('specifyTime') : null,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _endTimeController,
            label: AppLocalizations.get('endTime'),
            readOnly: true,
            onTap: _pickEndTime,
            suffixIcon: const Icon(Icons.access_time_outlined),
            validator: (_) =>
                _endTime == null ? AppLocalizations.get('specifyEndTime') : null,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _locationController,
            label: AppLocalizations.get('place'),
            validator: _required,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _registrationController,
            label: AppLocalizations.get('registrationUrl'),
            keyboardType: TextInputType.url,
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
          AppTextField(
            controller: _itEquipmentController,
            label: AppLocalizations.get('itEquipment'),
            hint: AppLocalizations.get('itEquipmentHint'),
            maxLines: 3,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _materialsController,
            label: AppLocalizations.get('materials'),
            hint: AppLocalizations.get('materialsHint'),
            maxLines: 3,
          ),
        ],
      ),
    );
  }

  Widget _buildBottomBar() {
    return SafeArea(
      top: false,
      child: Padding(
        padding: AppSpacing.screenPadding,
        child: Row(
          children: [
            if (_currentStep > 0) ...[
              Expanded(
                child: AppSecondaryButton(
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
                text: _currentStep < 2
                    ? AppLocalizations.get('next')
                    : AppLocalizations.get('sendRequest'),
                isLoading: _submitting,
                onPressed: _onPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
