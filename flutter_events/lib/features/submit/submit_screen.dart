import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../core/exceptions.dart';
import '../../models/category_model.dart';

class SubmitScreen extends StatefulWidget {
  const SubmitScreen({super.key});

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
  final _itEquipmentController = TextEditingController();
  final _materialsController = TextEditingController();

  int _currentStep = 0;
  int? _categoryId;
  DateTime? _date;
  TimeOfDay? _time;

  bool _categoriesLoading = true;
  String? _categoriesError;
  List<CategoryModel> _categories = [];

  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _loadCategories();
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

  String? _required(String? value) {
    if (value == null || value.trim().isEmpty) return 'Обязательное поле';
    return null;
  }

  void _onPrimary() {
    final valid = _formKeys[_currentStep].currentState?.validate() ?? false;
    if (!valid) return;
    if (_currentStep < 2) {
      setState(() => _currentStep++);
    } else {
      _submit();
    }
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

  String? _nullIfEmpty(String value) => value.trim().isEmpty ? null : value.trim();

  Future<void> _showSuccess(int eventId) {
    return showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return AlertDialog(
          icon: const Icon(Icons.check_circle, color: AppColors.success),
          title: const Text('Отправлено!'),
          content: const Text(
            'Модераторы рассмотрят в течение 1–2 рабочих дней.',
          ),
          actions: [
            AppTextButton(
              text: 'К ивентам',
              onPressed: () {
                Navigator.pop(dialogContext);
                Navigator.pop(context);
              },
            ),
          ],
        );
      },
    );
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AppAppBar(showBackButton: true, title: 'Новое мероприятие'),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_categoriesLoading) return const Center(child: AppLoader());
    if (_categoriesError != null) {
      return Center(
        child: Padding(
          padding: AppSpacing.screenPadding,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_categoriesError!, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.df),
              AppSecondaryButton(text: 'Повторить', onPressed: _loadCategories),
            ],
          ),
        ),
      );
    }

    return Column(
      children: [
        _buildProgress(),
        Expanded(
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
    const labels = ['Основное', 'Место и время', 'Ресурсы'];
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
                    color:
                        i == _currentStep ? AppColors.primary : AppColors.grey,
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
        return _stepBasic();
      case 1:
        return _stepPlaceTime();
      default:
        return _stepResources();
    }
  }

  Widget _stepBasic() {
    return Form(
      key: _formKeys[0],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppTextField(
            controller: _titleController,
            label: 'Название',
            validator: _required,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _descriptionController,
            label: 'Описание',
            maxLines: 4,
            validator: _required,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _organizerController,
            label: 'Организатор',
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
      decoration: const InputDecoration(labelText: 'Категория'),
      items: [
        for (final category in _categories)
          DropdownMenuItem(value: category.id, child: Text(category.name)),
      ],
      onChanged: (value) => setState(() => _categoryId = value),
      validator: (value) => value == null ? 'Выберите категорию' : null,
    );
  }

  Widget _stepPlaceTime() {
    return Form(
      key: _formKeys[1],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppTextField(
            controller: _dateController,
            label: 'Дата',
            readOnly: true,
            onTap: _pickDate,
            suffixIcon: const Icon(Icons.calendar_today_outlined),
            validator: (_) => _date == null ? 'Укажите дату' : null,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _timeController,
            label: 'Время',
            readOnly: true,
            onTap: _pickTime,
            suffixIcon: const Icon(Icons.access_time_outlined),
            validator: (_) => _time == null ? 'Укажите время' : null,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _locationController,
            label: 'Место',
            validator: _required,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _registrationController,
            label: 'Ссылка на регистрацию',
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
            label: 'IT-оборудование',
            hint: 'Проектор, ноутбуки, розетки...',
            maxLines: 3,
          ),
          const SizedBox(height: AppSpacing.df),
          AppTextField(
            controller: _materialsController,
            label: 'Материалы',
            hint: 'Маркеры, бумага А4, флипчарт...',
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
                  text: 'Назад',
                  onPressed: _submitting
                      ? null
                      : () => setState(() => _currentStep--),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
            ],
            Expanded(
              child: AppPrimaryButton(
                text: _currentStep < 2 ? 'Далее' : 'Отправить заявку',
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
