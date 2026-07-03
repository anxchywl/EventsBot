import 'package:app_ui/app_ui.dart';
import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_store.dart';
import '../../core/exceptions.dart';
import '../shell/app_shell.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    if (email.isEmpty || password.isEmpty) {
      _showMessage('Заполните все поля');
      return;
    }

    setState(() => _loading = true);
    try {
      final result = await login(email, password);
      await AuthStore.save(
        token: result.token,
        role: result.role,
        firstName: result.firstName,
        userId: result.userId,
      );
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const AppShell()),
      );
    } on ApiException catch (e) {
      _showMessage(e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: AppSpacing.screenPadding,
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: IntrinsicHeight(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Center(
                        child: Container(
                          width: 64,
                          height: 64,
                          decoration: BoxDecoration(
                            color: AppColors.primaryLight,
                            borderRadius:
                                BorderRadius.circular(AppSpacing.radiusDf),
                          ),
                          child: const Icon(
                            Icons.school,
                            color: AppColors.primary,
                            size: 32,
                          ),
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xl),
                      Text(
                        'Войти',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.headlineMedium,
                      ),
                      const SizedBox(height: AppSpacing.xxl),
                      AppTextField(
                        controller: _emailController,
                        label: 'Email',
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                      ),
                      const SizedBox(height: AppSpacing.df),
                      AppPasswordField(
                        controller: _passwordController,
                        label: 'Пароль',
                        onSubmitted: (_) => _submit(),
                      ),
                      const SizedBox(height: AppSpacing.xl),
                      AppPrimaryButton(
                        text: 'Войти',
                        isLoading: _loading,
                        onPressed: _submit,
                      ),
                      const SizedBox(height: AppSpacing.md),
                      AppTextButton(
                        text: 'Нет аккаунта? Зарегистрироваться',
                        onPressed: _loading
                            ? null
                            : () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => const RegisterScreen(),
                                  ),
                                ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
