import 'package:flutter/material.dart';

import 'package:english_day/core/theme/app_theme.dart';
import 'package:english_day/core/widgets/app_button.dart';
import 'package:english_day/core/widgets/app_text_field.dart';
import 'package:english_day/core/widgets/common.dart';
import 'package:english_day/dev/dummy_data.dart';
import 'package:english_day/features/reading/presentation/reading_story_screen.dart';

// ---------------------------------------------------------------- Settings
class ReadingSettingsScreen extends StatefulWidget {
  const ReadingSettingsScreen({super.key});

  @override
  State<ReadingSettingsScreen> createState() => _ReadingSettingsScreenState();
}

class _ReadingSettingsScreenState extends State<ReadingSettingsScreen> {
  int _level = 1;
  String? _topic = 'Budaya';

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Reading',
      bottom: AppButton(
        label: 'Buat cerita',
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ReadingStoryScreen(
            level: ReadingDummy.levels[_level].name,
            topic: _topic ?? 'Acak',
            initialState: StoryState.loading,
          ),
        )),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text('Level', style: AppText.h3),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            children: [
              for (var i = 0; i < ReadingDummy.levels.length; i++)
                AppChoiceChip(
                  label: ReadingDummy.levels[i].name,
                  subtitle: ReadingDummy.levels[i].cefr,
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
              for (final t in ReadingDummy.topics)
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
