import 'package:flutter/material.dart';

import 'package:english_day/core/config/app_info.dart';
import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/dev/demo_listening.dart';
import 'package:english_day/dev/demo_reading.dart';
import 'package:english_day/dev/demo_scope.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/dev/showcase/ai_status_showcase_screen.dart';
import 'package:english_day/dev/showcase/answers_showcase_screen.dart';
import 'package:english_day/dev/showcase/buttons_showcase_screen.dart';
import 'package:english_day/dev/showcase/inputs_showcase_screen.dart';
import 'package:english_day/features/auth/presentation/login_screen.dart';
import 'package:english_day/features/auth/presentation/register_screen.dart';
import 'package:english_day/features/auth/presentation/splash_screen.dart';
import 'package:english_day/features/dashboard/presentation/dashboard_screen.dart';
import 'package:english_day/features/listening/presentation/listening_screen.dart';
import 'package:english_day/features/profile/presentation/profile_screen.dart';
import 'package:english_day/features/reading/presentation/reading_quiz_screen.dart';
import 'package:english_day/features/reading/presentation/reading_result_screen.dart';
import 'package:english_day/features/reading/presentation/reading_settings_screen.dart';
import 'package:english_day/features/reading/presentation/reading_story_screen.dart';
import 'package:english_day/features/speaking/presentation/mic_permission_screen.dart';
import 'package:english_day/features/speaking/presentation/speaking_screen.dart';
import 'package:english_day/features/system/presentation/offline_screen.dart';
import 'package:english_day/features/writing/presentation/writing_input_screen.dart';
import 'package:english_day/features/writing/presentation/writing_result_screen.dart';

/// Galeri semua layar & state sesuai file desain, untuk review slicing.
class GalleryScreen extends StatelessWidget {
  const GalleryScreen({super.key});

  /// Every screen/state in the gallery, so tests can render each one.
  @visibleForTesting
  static Map<String, List<(String, WidgetBuilder)>> get entries => _groups;

  static final Map<String, List<(String, WidgetBuilder)>> _groups = {
    'Akun': [
      ('splash', (_) => const SplashScreen(autoNavigate: false)),
      ('login', (_) => const LoginScreen()),
      ('login-loading', (_) => const _FrozenLogin()),
      ('login-error', (_) => const LoginScreen(initialState: LoginState.error)),
      ('register', (_) => const RegisterScreen()),
      ('register-error', (_) => const RegisterScreen(showErrors: true)),
    ],
    'Dashboard': [
      ('lanjutkan latihan', (_) => const DemoScope(child: DashboardScreen())),
      ('pengguna baru', (_) => const DemoScope(withResume: false, child: DashboardScreen())),
    ],
    'Global': [
      ('banner AI', (_) => const AiStatusScreen()),
      ('offline', (_) => const OfflineScreen()),
      ('sesi habis', (_) => const DemoScope(child: DashboardScreen(showSessionExpired: true))),
      (
        'teks disalin',
        (_) => WritingResultScreen(result: WritingDummy.result, autoCopy: true)
      ),
    ],
    'Izin mikrofon': [
      ('permintaan', (_) => const MicPermissionScreen()),
      ('ditolak permanen', (_) => const MicPermissionScreen(permanentlyDenied: true)),
    ],
    'Komponen': [
      ('input dan pilihan', (_) => const InputsShowcaseScreen()),
      ('jawaban dan percakapan', (_) => const AnswersShowcaseScreen()),
      ('tombol', (_) => const ButtonsShowcaseScreen()),
    ],
    'Profil': [
      ('profil', (_) => const DemoScope(child: ProfileScreen())),
      ('konfirmasi keluar', (_) => const DemoScope(child: ProfileScreen(showLogoutConfirm: true))),
    ],
    'Writing': [
      ('input empty', (_) => const WritingInputScreen()),
      ('input filled', (_) => const WritingInputScreen(initialText: WritingDummy.sampleInput)),
      (
        'input loading',
        (_) => const WritingInputScreen(
            initialText: WritingDummy.sampleInput, initialState: WritingState.loading)
      ),
      (
        'input slow',
        (_) => const WritingInputScreen(
            initialText: WritingDummy.sampleInput, initialState: WritingState.slow)
      ),
      (
        'input error',
        (_) => const WritingInputScreen(
            initialText: WritingDummy.sampleInput, initialState: WritingState.error)
      ),
      ('input limit', (_) => const WritingInputScreen(initialText: WritingDummy.longInput)),
      (
        'hasil loading',
        (_) => const WritingResultScreen(result: null)
      ),
      (
        'hasil corrections',
        (_) => WritingResultScreen(result: WritingDummy.result)
      ),
      (
        'hasil sheet',
        (_) => WritingResultScreen(result: WritingDummy.result, openRuleSheet: true)
      ),
      (
        'hasil correct',
        (_) => WritingResultScreen(result: WritingDummy.correctResult)
      ),
    ],
    'Reading': [
      ('pengaturan', (_) => const ReadingSettingsScreen()),
      (
        'cerita loading',
        (_) => ReadingStoryScreen(
            practice: DemoReadingPractice(loaded: false),
            initialState: StoryState.loading,
            autoLoad: false)
      ),
      (
        'cerita slow',
        (_) => ReadingStoryScreen(
            practice: DemoReadingPractice(loaded: false), initialState: StoryState.slow)
      ),
      (
        'cerita error',
        (_) => ReadingStoryScreen(
            practice: DemoReadingPractice(loaded: false), initialState: StoryState.error)
      ),
      ('cerita story', (_) => ReadingStoryScreen(practice: DemoReadingPractice())),
      (
        'cerita continuation',
        (_) => ReadingStoryScreen(practice: DemoReadingPractice(), scrollToEnd: true)
      ),
      (
        'cerita sheet',
        (_) => ReadingStoryScreen(practice: DemoReadingPractice(), openVocab: 'drifted')
      ),
      ('kuis empty', (_) => ReadingQuizScreen(practice: DemoReadingPractice(), initialIndex: 1)),
      (
        'kuis selected',
        (_) => ReadingQuizScreen(
            practice: DemoReadingPractice(), initialIndex: 1, initialSelected: 1)
      ),
      (
        'kuis correct',
        (_) => ReadingQuizScreen(
            practice: DemoReadingPractice(),
            initialIndex: 1,
            initialSelected: 1,
            initialSubmitted: true)
      ),
      (
        'kuis wrong',
        (_) => ReadingQuizScreen(
            practice: DemoReadingPractice(),
            initialIndex: 1,
            initialSelected: 2,
            initialSubmitted: true)
      ),
      (
        'kuis result',
        (_) {
          final demo = DemoReadingPractice(answered: [1, 1, 2, 0, 1]);
          return ReadingResultScreen(
              story: DemoReadingPractice.demoStory, answers: demo.answers, summary: demo.summary);
        }
      ),
    ],
    'Speaking': [
      ('empty', (_) => const SpeakingScreen()),
      ('idle', (_) => const SpeakingScreen(withHistory: true)),
      (
        'recording',
        (_) => const SpeakingScreen(withHistory: true, initialState: SpeakingState.recording)
      ),
      (
        'processing',
        (_) => const SpeakingScreen(withHistory: true, initialState: SpeakingState.processing)
      ),
      (
        'speaking',
        (_) => const SpeakingScreen(withHistory: true, initialState: SpeakingState.aiSpeaking)
      ),
      (
        'slow',
        (_) => const SpeakingScreen(withHistory: true, initialState: SpeakingState.slow)
      ),
      (
        'error',
        (_) => const SpeakingScreen(withHistory: true, initialState: SpeakingState.error)
      ),
    ],
    'Listening': [
      ('empty', (_) => ListeningScreen(practice: DemoListeningPractice(loaded: false))),
      (
        'loading',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(loaded: false),
            initialPhase: ListeningPhase.loading,
            freeze: true)
      ),
      (
        'slow',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(loaded: false),
            initialPhase: ListeningPhase.slow,
            freeze: true)
      ),
      (
        'playing',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(answers: [0, null, null]),
            initialPhase: ListeningPhase.practice,
            autoPlay: true)
      ),
      (
        'questions',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(answers: [0, 1, 2]),
            initialPhase: ListeningPhase.practice)
      ),
      (
        'locked',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(answers: [0, 1, 2]),
            initialPhase: ListeningPhase.practice,
            scrollToLast: true)
      ),
      (
        'error',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(answers: [0, null, null]),
            initialPhase: ListeningPhase.audioError)
      ),
      (
        'result',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(answers: [0, 1, 2], submitted: true),
            initialPhase: ListeningPhase.result)
      ),
      (
        'review',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(answers: [0, 1, 2], submitted: true),
            initialPhase: ListeningPhase.result,
            focus: ResultFocus.review)
      ),
      (
        'transcript',
        (_) => ListeningScreen(
            practice: DemoListeningPractice(answers: [0, 1, 2], submitted: true),
            initialPhase: ListeningPhase.result,
            focus: ResultFocus.transcript)
      ),
    ],
  };

  @override
  Widget build(BuildContext context) {
    final total = _groups.values.fold<int>(0, (a, b) => a + b.length);
    return AppScaffold(
      title: 'Tentang aplikasi',
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          Text(AppInfo.appName, style: AppText.display),
          const SizedBox(height: 4),
          Text('${AppInfo.tagline} · Versi ${AppInfo.version}', style: AppText.caption),
          const SizedBox(height: 24),
          Text('Galeri UI ($total layar)', style: AppText.h3),
          const SizedBox(height: 4),
          Text('Buka setiap layar & state sesuai file desain. Semua data adalah dummy.',
              style: AppText.caption),
          const SizedBox(height: 16),
          for (final entry in _groups.entries) ...[
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 8),
              child: Text(entry.key,
                  style: AppText.sans(
                      size: 14, weight: FontWeight.w700, color: AppColors.primary)),
            ),
            AppCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  for (var i = 0; i < entry.value.length; i++)
                    InkWell(
                      onTap: () => Navigator.of(context)
                          .push(MaterialPageRoute(builder: entry.value[i].$2)),
                      child: Container(
                        height: 52,
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        decoration: BoxDecoration(
                          border: i == entry.value.length - 1
                              ? null
                              : const Border(bottom: BorderSide(color: AppColors.divider)),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text('${entry.key} · ${entry.value[i].$1}',
                                  style: AppText.sans(size: 15, weight: FontWeight.w500)),
                            ),
                            const Icon(Icons.chevron_right, color: AppColors.primary),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Login dalam state loading (statis, untuk galeri).
class _FrozenLogin extends StatelessWidget {
  const _FrozenLogin();

  @override
  Widget build(BuildContext context) => const LoginScreen(initialState: LoginState.loading);
}
