import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/features/reading/application/reading_session.dart';
import 'package:english_day/features/reading/data/reading_models.dart';
import 'package:english_day/features/reading/data/reading_repository.dart';
import 'package:english_day/features/reading/presentation/reading_story_screen.dart';

// ---------------------------------------------------------------- Settings
class ReadingSettingsScreen extends ConsumerStatefulWidget {
  const ReadingSettingsScreen({super.key});

  @override
  ConsumerState<ReadingSettingsScreen> createState() => _ReadingSettingsScreenState();
}

class _ReadingSettingsScreenState extends ConsumerState<ReadingSettingsScreen> {
  int _level = 1;
  String? _topic = 'Budaya';

  void _create() {
    final practice = ReadingSession(
      ref.read(readingRepositoryProvider),
      request: ReadingRequest(level: ReadingLevel.all[_level], topic: _topic),
    );
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ReadingStoryScreen(practice: practice),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Reading',
      bottom: AppButton(label: 'Buat cerita', onPressed: _create),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text('Level', style: AppText.h3),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            children: [
              for (var i = 0; i < ReadingLevel.all.length; i++)
                AppChoiceChip(
                  label: ReadingLevel.all[i].name,
                  subtitle: ReadingLevel.all[i].cefr,
                  selected: _level == i,
                  onTap: () => setState(() => _level = i),
                ),
            ],
          ),
          const SizedBox(height: 28),
          Text('Topik (opsional)', style: AppText.h3),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 12,
            children: [
              for (final t in readingTopics)
                AppChoiceChip(
                  label: t,
                  selected: _topic == t,
                  onTap: () => setState(() => _topic = _topic == t ? null : t),
                ),
            ],
          ),
          const SizedBox(height: 24),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.menu_book_outlined, color: AppColors.primary),
                const SizedBox(height: 16),
                Text('Cerita sekitar 150–250 kata, diikuti 5 soal pilihan ganda.',
                    style: AppText.body),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
