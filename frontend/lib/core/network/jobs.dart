import 'dart:math' as math;

import 'package:english_day/core/network/api_client.dart';

/// One piece of async AI work (`Job`): exercise generation, evaluation, grading,
/// voice turns. Created by a POST, then polled with `GET /jobs/{job_id}`.
class Job {
  const Job({
    required this.id,
    required this.type,
    required this.status,
    this.errorCode,
    this.canCancel = false,
    this.canRetry = false,
    this.resultRefs = const {},
  });

  factory Job.fromJson(Map<String, dynamic> json) => Job(
        id: json['job_id'] as String,
        type: json['job_type'] as String,
        status: json['status'] as String,
        errorCode: (json['error'] as Map<String, dynamic>?)?['code'] as String?,
        canCancel: json['can_cancel'] == true,
        canRetry: json['can_retry'] == true,
        resultRefs: {
          for (final e in ((json['result_refs'] as Map?) ?? const {}).entries)
            e.key as String: e.value as String,
        },
      );

  final String id;

  /// generate_exercise | evaluate_attempt | grade_answer | start_conversation | process_voice_turn
  final String type;

  /// queued | running | cancel_requested | succeeded | failed | cancelled
  final String status;
  final String? errorCode;
  final bool canCancel;
  final bool canRetry;

  /// Public IDs produced by the job (exercise_id, evaluation_id, message_id, ...).
  final Map<String, String> resultRefs;

  bool get succeeded => status == 'succeeded';
  bool get isFinished => succeeded || status == 'failed' || status == 'cancelled';
}

/// The AI job ended without a result (failed or cancelled).
class JobFailedException implements Exception {
  const JobFailedException(this.job);
  final Job job;

  @override
  String toString() => 'JobFailedException(${job.type} ${job.status} ${job.errorCode})';
}

/// The AI job is still running after the wait limit. Waiting again later is safe.
class JobTimeoutException implements Exception {
  const JobTimeoutException(this.jobId);
  final String jobId;

  @override
  String toString() => 'JobTimeoutException($jobId)';
}

/// The user stopped waiting (e.g. "Batalkan").
class OperationCancelledException implements Exception {
  const OperationCancelledException();
}

/// Polls `GET /jobs/{jobId}` with growing pauses (0.4 s → 3 s) until the job finishes.
///
/// Returns the succeeded job; throws [JobFailedException] when it failed or was
/// cancelled, [JobTimeoutException] after [timeout], and
/// [OperationCancelledException] as soon as [isCancelled] returns true.
Future<Job> waitForJob(
  ApiClient api,
  String jobId, {
  Duration timeout = const Duration(seconds: 90),
  bool Function()? isCancelled,
}) async {
  var pause = const Duration(milliseconds: 400);
  var waited = Duration.zero;
  while (true) {
    if (isCancelled?.call() ?? false) throw const OperationCancelledException();
    final job = Job.fromJson(await api.get('/jobs/$jobId') as Map<String, dynamic>);
    if (job.succeeded) return job;
    if (job.isFinished) throw JobFailedException(job);
    if (waited >= timeout) throw JobTimeoutException(jobId);
    await Future<void>.delayed(pause);
    waited += pause;
    pause = Duration(milliseconds: math.min(pause.inMilliseconds * 3 ~/ 2, 3000));
  }
}
