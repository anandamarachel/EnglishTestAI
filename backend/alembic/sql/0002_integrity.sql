-- Frozen with revision 0002. Future changes require a new migration.
-- Cross-row checks run at commit; aggregate locks serialize ordinary READ COMMITTED writes.
CREATE FUNCTION ep_assert(valid boolean, reason text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  IF valid IS DISTINCT FROM true THEN
    RAISE EXCEPTION '%', reason USING ERRCODE = '23514', CONSTRAINT = 'domain_integrity';
  END IF;
END $$;

CREATE FUNCTION ep_validate_spans(source_text text, spans jsonb) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE span jsonb; first_pos integer; last_pos integer;
BEGIN
  PERFORM ep_assert(jsonb_typeof(spans) = 'array', 'Text spans must be an array');
  FOR span IN SELECT value FROM jsonb_array_elements(spans) LOOP
    PERFORM ep_assert(jsonb_typeof(span) = 'object'
      AND jsonb_typeof(span->'start') = 'number' AND jsonb_typeof(span->'end') = 'number'
      AND (span->>'start') ~ '^[0-9]{1,9}$' AND (span->>'end') ~ '^[0-9]{1,9}$'
      AND jsonb_typeof(span->'original') = 'string', 'Invalid text span');
    first_pos := (span->>'start')::integer; last_pos := (span->>'end')::integer;
    PERFORM ep_assert(first_pos <= last_pos AND last_pos <= char_length(source_text)
      AND substring(source_text FROM first_pos + 1 FOR last_pos - first_pos) = span->>'original',
      'Text span does not match immutable source');
  END LOOP;
END $$;

CREATE FUNCTION ep_exercise_ids(table_name text, row_data jsonb) RETURNS SETOF uuid
LANGUAGE plpgsql AS $$
BEGIN
  CASE table_name
    WHEN 'exercises', 'writing_exercises', 'reading_exercises', 'listening_exercises',
         'speaking_exercises', 'questions', 'exercise_vocabulary', 'attempts' THEN
      RETURN QUERY SELECT (row_data->>'exercise_id')::uuid;
    WHEN 'question_options' THEN
      RETURN QUERY SELECT exercise_id FROM questions WHERE question_id = (row_data->>'question_id')::uuid;
    WHEN 'writing_attempts', 'reading_attempts', 'listening_attempts', 'answers',
         'evaluations', 'conversation_sessions' THEN
      RETURN QUERY SELECT exercise_id FROM attempts WHERE attempt_id = (row_data->>'attempt_id')::uuid;
    WHEN 'criterion_results' THEN
      RETURN QUERY SELECT a.exercise_id FROM evaluations e JOIN attempts a USING (attempt_id)
        WHERE e.evaluation_id = (row_data->>'evaluation_id')::uuid;
    WHEN 'conversation_messages' THEN
      RETURN QUERY SELECT a.exercise_id FROM conversation_sessions s JOIN attempts a USING (attempt_id)
        WHERE s.conversation_session_id = (row_data->>'conversation_session_id')::uuid;
    WHEN 'ai_jobs' THEN
      RETURN QUERY SELECT (row_data->>'exercise_id')::uuid WHERE row_data->>'exercise_id' IS NOT NULL
        UNION SELECT exercise_id FROM attempts WHERE attempt_id = (row_data->>'attempt_id')::uuid
        UNION SELECT a.exercise_id FROM answers x JOIN attempts a USING (attempt_id)
          WHERE x.answer_id = (row_data->>'answer_id')::uuid
        UNION SELECT a.exercise_id FROM conversation_messages m
          JOIN conversation_sessions s USING (conversation_session_id) JOIN attempts a USING (attempt_id)
          WHERE m.message_id = (row_data->>'message_id')::uuid;
    WHEN 'media_assets' THEN
      RETURN QUERY SELECT exercise_id FROM listening_exercises WHERE audio_media_id = (row_data->>'media_id')::uuid
        UNION SELECT a.exercise_id FROM conversation_messages m
          JOIN conversation_sessions s USING (conversation_session_id) JOIN attempts a USING (attempt_id)
          WHERE m.audio_media_id = (row_data->>'media_id')::uuid;
    ELSE NULL;
  END CASE;
END $$;

CREATE FUNCTION ep_guard_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_data jsonb := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) ELSE '{}'::jsonb END;
        new_data jsonb := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) ELSE '{}'::jsonb END;
        eid uuid; attempt_row attempts%ROWTYPE; key_name text; locked boolean;
BEGIN
  -- Lock every affected exercise in a consistent order before checking or mutating descendants.
  FOR eid IN SELECT id FROM (
      SELECT ep_exercise_ids(TG_TABLE_NAME, old_data) AS id
      UNION SELECT ep_exercise_ids(TG_TABLE_NAME, new_data) AS id
    ) affected WHERE id IS NOT NULL ORDER BY id LOOP
    PERFORM 1 FROM exercises WHERE exercise_id = eid FOR UPDATE;
    IF TG_TABLE_NAME IN ('exercises','writing_exercises','reading_exercises','listening_exercises',
                        'speaking_exercises','questions','question_options','exercise_vocabulary') THEN
      SELECT EXISTS (SELECT 1 FROM attempts WHERE exercise_id = eid) INTO locked;
      PERFORM ep_assert(NOT locked OR (TG_OP = 'UPDATE' AND old_data = new_data),
        'Exercise content is immutable after an attempt exists');
    END IF;
  END LOOP;

  IF TG_OP = 'UPDATE' THEN
    -- Identity and ownership cannot be moved to a different aggregate after insertion.
    FOREACH key_name IN ARRAY string_to_array(TG_ARGV[0], ',') LOOP
      PERFORM ep_assert(old_data->key_name IS NOT DISTINCT FROM new_data->key_name,
        'Identity and ownership fields are immutable');
    END LOOP;
    IF old_data ? 'revision' THEN
      PERFORM ep_assert((new_data->>'revision')::integer >= (old_data->>'revision')::integer,
        'Revision cannot decrease');
    END IF;
    IF TG_TABLE_NAME = 'attempts' THEN
      PERFORM ep_assert(OLD.submitted_at IS NULL OR NEW.submitted_at IS NOT DISTINCT FROM OLD.submitted_at,
        'Submission timestamp cannot be cleared or changed');
      PERFORM ep_assert(OLD.submitted_at IS NULL OR NEW.status <> 'in_progress',
        'A submitted attempt cannot return to draft');
      PERFORM ep_assert(OLD.status NOT IN ('completed','cancelled') OR NEW.status = OLD.status,
        'A terminal attempt cannot be reopened');
    ELSIF TG_TABLE_NAME = 'answers' THEN
      PERFORM ep_assert(OLD.submitted_at IS NULL OR
        (NEW.selected_option_id IS NOT DISTINCT FROM OLD.selected_option_id
         AND NEW.response_text IS NOT DISTINCT FROM OLD.response_text
         AND NEW.submitted_at IS NOT DISTINCT FROM OLD.submitted_at), 'Submitted answers are immutable');
      PERFORM ep_assert(OLD.grading_status <> 'graded' OR
        (NEW.awarded_points IS NOT DISTINCT FROM OLD.awarded_points AND NEW.grading_status = 'graded'
         AND NEW.feedback IS NOT DISTINCT FROM OLD.feedback
         AND NEW.grading_model_version IS NOT DISTINCT FROM OLD.grading_model_version),
         'Completed answer grades are immutable');
    ELSIF TG_TABLE_NAME IN ('writing_attempts','reading_attempts','listening_attempts') THEN
      SELECT * INTO attempt_row FROM attempts WHERE attempt_id = (new_data->>'attempt_id')::uuid;
      PERFORM ep_assert((attempt_row.submitted_at IS NULL AND attempt_row.status = 'in_progress')
        OR old_data = new_data, 'Submitted or cancelled attempt content is immutable');
    ELSIF TG_TABLE_NAME = 'conversation_sessions' THEN
      PERFORM ep_assert(OLD.status <> 'ended' OR old_data = new_data, 'Ended conversations are immutable');
    ELSIF TG_TABLE_NAME = 'conversation_messages' THEN
      PERFORM ep_assert(OLD.delivery_status <> 'ready' OR old_data = new_data, 'Ready messages are immutable');
    ELSIF TG_TABLE_NAME = 'ai_jobs' THEN
      PERFORM ep_assert(NEW.execution_version >= OLD.execution_version, 'Execution version cannot decrease');
      PERFORM ep_assert(OLD.status <> 'succeeded' OR old_data = new_data, 'Succeeded jobs are immutable');
      IF OLD.status IN ('failed','cancelled') AND NEW.status <> OLD.status THEN
        PERFORM ep_assert(NEW.status = 'queued' AND NEW.execution_version > OLD.execution_version
          AND NEW.attempt_count = 0, 'Retry requires a fresh execution version');
      ELSIF OLD.status = 'cancel_requested' THEN
        PERFORM ep_assert(NEW.status IN ('cancel_requested','cancelled'), 'Cancelled execution cannot commit results');
      ELSIF OLD.status = 'queued' THEN
        PERFORM ep_assert(NEW.status IN ('queued','running','cancelled'), 'Invalid queued job transition');
      ELSIF OLD.status = 'running' THEN
        PERFORM ep_assert(NEW.status IN ('running','queued','succeeded','failed','cancel_requested'),
          'Invalid running job transition');
      END IF;
      IF NEW.status = 'cancel_requested' AND OLD.status <> 'cancel_requested' THEN
        PERFORM ep_assert(NEW.execution_version > OLD.execution_version, 'Cancellation must invalidate the execution');
      END IF;
    END IF;
  END IF;
  -- Taking a media lock closes the race between accepting an upload and deleting/changing it.
  IF new_data->>'audio_media_id' IS NOT NULL THEN
    PERFORM 1 FROM media_assets WHERE media_id = (new_data->>'audio_media_id')::uuid FOR SHARE;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ep_validate_exercise(eid uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE e exercises%ROWTYPE; q questions%ROWTYPE; attempt_record attempts%ROWTYPE;
        m record; ev record; glossary record; n integer; expected integer; source_text text;
        correction jsonb; previous_end integer; previous_start integer; correction_ids text[];
BEGIN
  SELECT * INTO e FROM exercises WHERE exercise_id = eid;
  IF NOT FOUND THEN RETURN; END IF;

  PERFORM ep_assert(NOT EXISTS (
    SELECT 1 FROM (
      SELECT 'writing' AS skill FROM writing_exercises WHERE exercise_id = eid
      UNION ALL SELECT 'reading' FROM reading_exercises WHERE exercise_id = eid
      UNION ALL SELECT 'listening' FROM listening_exercises WHERE exercise_id = eid
      UNION ALL SELECT 'speaking' FROM speaking_exercises WHERE exercise_id = eid
    ) detail WHERE detail.skill <> e.skill), 'Exercise detail does not match skill');
  SELECT (SELECT count(*) FROM writing_exercises WHERE exercise_id=eid)
       + (SELECT count(*) FROM reading_exercises WHERE exercise_id=eid)
       + (SELECT count(*) FROM listening_exercises WHERE exercise_id=eid)
       + (SELECT count(*) FROM speaking_exercises WHERE exercise_id=eid) INTO n;
  PERFORM ep_assert(e.generation_status <> 'ready' OR n=1, 'Ready exercise requires exactly one skill detail');
  IF e.skill NOT IN ('reading','listening') THEN
    PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM questions WHERE exercise_id=eid), 'Only quiz skills have questions');
  END IF;
  IF e.skill <> 'reading' THEN
    PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM exercise_vocabulary WHERE exercise_id=eid), 'Vocabulary requires Reading');
  END IF;
  IF e.skill = 'listening' THEN
    SELECT l.audio_media_id, x.owner_user_id, x.purpose, x.status INTO m
      FROM listening_exercises l LEFT JOIN media_assets x ON x.media_id=l.audio_media_id WHERE l.exercise_id=eid;
    IF m.audio_media_id IS NOT NULL THEN
      PERFORM ep_assert(m.owner_user_id=e.created_by AND m.purpose='listening_audio', 'Invalid Listening media ownership or purpose');
    END IF;
    PERFORM ep_assert(e.generation_status <> 'ready' OR (m.audio_media_id IS NOT NULL
      AND (m.status='ready' OR (m.status='deleted' AND EXISTS(SELECT 1 FROM attempts WHERE exercise_id=eid)))),
      'Ready Listening exercise requires ready audio');
  END IF;
  IF e.skill IN ('reading','listening') AND e.generation_status='ready' THEN
    IF e.skill='reading' THEN SELECT question_count INTO expected FROM reading_exercises WHERE exercise_id=eid;
    ELSE SELECT question_count INTO expected FROM listening_exercises WHERE exercise_id=eid; END IF;
    SELECT count(*) INTO n FROM questions WHERE exercise_id=eid;
    PERFORM ep_assert(n=expected, 'Ready exercise question count does not match configuration');
    PERFORM ep_assert((SELECT min(position)=1 AND max(position)=count(*) FROM questions WHERE exercise_id=eid),
      'Question positions must be contiguous');
  END IF;
  IF e.skill='reading' THEN SELECT passage INTO source_text FROM reading_exercises WHERE exercise_id=eid;
  ELSIF e.skill='listening' THEN SELECT transcript INTO source_text FROM listening_exercises WHERE exercise_id=eid; END IF;

  FOR q IN SELECT * FROM questions WHERE exercise_id=eid LOOP
    IF q.question_type='short_answer' THEN
      PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM question_options WHERE question_id=q.question_id), 'Short answers cannot have choices');
    ELSIF e.generation_status='ready' THEN
      PERFORM ep_assert((SELECT count(*)>=2 AND count(*) FILTER(WHERE is_correct)=1
        AND min(position)=1 AND max(position)=count(*) FROM question_options WHERE question_id=q.question_id),
        'Ready multiple-choice question requires ordered choices and exactly one correct choice');
    END IF;
    PERFORM ep_validate_spans(source_text, q.evidence_spans);
  END LOOP;
  FOR glossary IN SELECT * FROM exercise_vocabulary WHERE exercise_id=eid LOOP
    PERFORM ep_validate_spans(source_text, glossary.occurrences);
  END LOOP;

  FOR attempt_record IN SELECT * FROM attempts WHERE exercise_id=eid LOOP
    PERFORM ep_assert(attempt_record.user_id=e.created_by AND e.generation_status='ready', 'Attempt requires an owned ready exercise');
    IF attempt_record.source_attempt_id IS NOT NULL THEN
      PERFORM ep_assert(e.skill='writing' AND EXISTS(SELECT 1 FROM attempts s WHERE s.attempt_id=attempt_record.source_attempt_id
        AND s.user_id=attempt_record.user_id AND s.exercise_id=eid AND s.submitted_at IS NOT NULL), 'Invalid Writing source attempt');
    END IF;
    SELECT (SELECT count(*) FROM writing_attempts WHERE attempt_id=attempt_record.attempt_id)
         + (SELECT count(*) FROM reading_attempts WHERE attempt_id=attempt_record.attempt_id)
         + (SELECT count(*) FROM listening_attempts WHERE attempt_id=attempt_record.attempt_id)
         + (SELECT count(*) FROM conversation_sessions WHERE attempt_id=attempt_record.attempt_id) INTO n;
    PERFORM ep_assert(n=1 AND (
      (e.skill='writing' AND EXISTS(SELECT 1 FROM writing_attempts WHERE attempt_id=attempt_record.attempt_id)) OR
      (e.skill='reading' AND EXISTS(SELECT 1 FROM reading_attempts WHERE attempt_id=attempt_record.attempt_id)) OR
      (e.skill='listening' AND EXISTS(SELECT 1 FROM listening_attempts WHERE attempt_id=attempt_record.attempt_id)) OR
      (e.skill='speaking' AND EXISTS(SELECT 1 FROM conversation_sessions WHERE attempt_id=attempt_record.attempt_id))),
      'Attempt requires exactly one matching skill detail');
    PERFORM ep_assert(attempt_record.status='cancelled' OR
      (attempt_record.status='in_progress' AND ((e.skill='writing' AND attempt_record.current_stage='writing') OR
        (e.skill='reading' AND attempt_record.current_stage IN ('reading','quiz')) OR
        (e.skill='listening' AND attempt_record.current_stage IN ('listening','quiz')) OR
        (e.skill='speaking' AND attempt_record.current_stage='conversation'))) OR
      (attempt_record.status IN ('submitted','evaluating','failed') AND attempt_record.current_stage='evaluation') OR
      (attempt_record.status='completed' AND attempt_record.current_stage='results'), 'Attempt stage does not match skill/status');

    PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM (
      SELECT current_question_id FROM reading_attempts WHERE attempt_id=attempt_record.attempt_id
      UNION ALL SELECT current_question_id FROM listening_attempts WHERE attempt_id=attempt_record.attempt_id
    ) progress WHERE current_question_id IS NOT NULL AND NOT EXISTS
      (SELECT 1 FROM questions WHERE question_id=progress.current_question_id AND exercise_id=eid)),
      'Progress question belongs to a different exercise');
    PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM answers x JOIN questions z ON z.question_id=x.question_id
      LEFT JOIN question_options o ON o.option_id=x.selected_option_id WHERE x.attempt_id=attempt_record.attempt_id AND
      (z.exercise_id<>eid OR e.skill NOT IN ('reading','listening') OR
       (x.selected_option_id IS NOT NULL AND (o.question_id<>z.question_id OR z.question_type<>'multiple_choice')) OR
       (x.response_text IS NOT NULL AND z.question_type<>'short_answer') OR
       (x.awarded_points IS NOT NULL AND x.awarded_points>z.max_points))), 'Answer question, option, format, or points are invalid');

    IF attempt_record.submitted_at IS NOT NULL AND attempt_record.status<>'cancelled' THEN
      IF e.skill IN ('reading','listening') THEN
        PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM questions z WHERE z.exercise_id=eid AND NOT EXISTS
          (SELECT 1 FROM answers x WHERE x.attempt_id=attempt_record.attempt_id AND x.question_id=z.question_id AND x.submitted_at IS NOT NULL)),
          'Submitted quiz requires all answers');
        IF e.skill='reading' OR attempt_record.status='completed' THEN
          PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM answers WHERE attempt_id=attempt_record.attempt_id AND grading_status<>'graded'),
            'Quiz cannot complete before grading finishes');
        END IF;
      ELSIF e.skill='writing' THEN
        PERFORM ep_assert(EXISTS(SELECT 1 FROM writing_attempts WHERE attempt_id=attempt_record.attempt_id AND length(btrim(response_text))>0),
          'Cannot submit empty Writing');
      ELSIF e.skill='speaking' THEN
        PERFORM ep_assert(EXISTS(SELECT 1 FROM conversation_messages cm JOIN conversation_sessions cs USING(conversation_session_id)
          WHERE cs.attempt_id=attempt_record.attempt_id AND cm.sender='user' AND cm.delivery_status='ready'), 'Cannot finish empty Speaking session');
      END IF;
    END IF;
    PERFORM ep_assert(attempt_record.status<>'completed' OR EXISTS(SELECT 1 FROM evaluations WHERE attempt_id=attempt_record.attempt_id AND status='completed'),
      'Completed attempt requires completed evaluation');
  END LOOP;

  PERFORM ep_assert(NOT EXISTS(
    WITH RECURSIVE chain AS (
      SELECT attempt_id, source_attempt_id, ARRAY[attempt_id] AS path, false AS cycle FROM attempts WHERE exercise_id=eid
      UNION ALL SELECT s.attempt_id, s.source_attempt_id, c.path || s.attempt_id, s.attempt_id=ANY(c.path)
        FROM chain c JOIN attempts s ON s.attempt_id=c.source_attempt_id WHERE NOT c.cycle
    ) SELECT 1 FROM chain WHERE cycle), 'Writing source attempts cannot form a cycle');

  FOR ev IN SELECT v.*, a.status AS attempt_status, a.submitted_at, w.response_text
    FROM evaluations v JOIN attempts a USING(attempt_id) LEFT JOIN writing_attempts w USING(attempt_id)
    WHERE a.exercise_id=eid LOOP
    PERFORM ep_assert(ev.submitted_at IS NOT NULL, 'Evaluation requires submitted attempt');
    PERFORM ep_assert(ev.status<>'completed' OR ev.attempt_status='completed', 'Evaluation and attempt completion must agree');
    PERFORM ep_assert(ev.overall_score IS NULL OR NOT EXISTS(
      SELECT 1 FROM jsonb_array_elements(COALESCE(ev.rubric_snapshot->'criteria','[]'::jsonb)) item
      WHERE item->>'required'='true' AND NOT EXISTS(SELECT 1 FROM criterion_results c
        WHERE c.evaluation_id=ev.evaluation_id AND c.criterion_code=item->>'code'
          AND c.assessment_status='assessed')),
      'Cannot give overall score with an unassessed required criterion');
    PERFORM ep_assert(ev.feedback_payload->>'schema_version'='1'
      AND jsonb_typeof(ev.feedback_payload->'corrections')='array'
      AND jsonb_typeof(ev.feedback_payload->'limitations')='array', 'Invalid feedback payload shape');
    IF e.skill <> 'writing' THEN
      PERFORM ep_assert(jsonb_array_length(ev.feedback_payload->'corrections')=0, 'Only Writing has text corrections');
    ELSE
      PERFORM ep_validate_spans(ev.response_text, ev.feedback_payload->'corrections');
      previous_end := -1; previous_start := -1; correction_ids := ARRAY[]::text[];
      FOR correction IN SELECT value FROM jsonb_array_elements(ev.feedback_payload->'corrections') LOOP
        PERFORM ep_assert(jsonb_typeof(correction->'correction_id')='string'
          AND length(correction->>'correction_id')>0
          AND NOT (correction->>'correction_id'=ANY(correction_ids))
          AND jsonb_typeof(correction->'replacement')='string'
          AND correction->>'category' IN ('grammar','spelling','vocabulary','style')
          AND jsonb_typeof(correction->'title')='string'
          AND jsonb_typeof(correction->'explanation')='string'
          AND jsonb_typeof(correction->'example')='string', 'Invalid correction attributes');
        PERFORM ep_assert((correction->>'start')::integer >= previous_end
          AND (correction->>'start')::integer > previous_start, 'Corrections must be ordered and nonoverlapping');
        previous_start := (correction->>'start')::integer; previous_end := (correction->>'end')::integer;
        correction_ids := array_append(correction_ids, correction->>'correction_id');
      END LOOP;
    END IF;
  END LOOP;

  FOR m IN SELECT s.*, a.status AS attempt_status FROM conversation_sessions s JOIN attempts a USING(attempt_id)
    WHERE a.exercise_id=eid LOOP
    PERFORM ep_assert(e.skill='speaking', 'Conversation requires Speaking');
    PERFORM ep_assert((m.status='ended') = (m.attempt_status <> 'in_progress'), 'Conversation and attempt lifecycle must agree');
    PERFORM ep_assert(m.next_position > COALESCE((SELECT max(position) FROM conversation_messages WHERE conversation_session_id=m.conversation_session_id),0),
      'Conversation next position must follow its messages');
    PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM conversation_messages cm LEFT JOIN conversation_messages original ON original.message_id=cm.reply_to_message_id
      LEFT JOIN media_assets asset ON asset.media_id=cm.audio_media_id WHERE cm.conversation_session_id=m.conversation_session_id AND
      ((cm.reply_to_message_id IS NOT NULL AND (original.sender<>'user' OR original.conversation_session_id<>cm.conversation_session_id)) OR
       (cm.audio_media_id IS NOT NULL AND (asset.owner_user_id<>e.created_by OR
         asset.purpose<>CASE WHEN cm.sender='user' THEN 'speaking_user_audio' ELSE 'speaking_ai_audio' END)) OR
       (cm.delivery_status='ready' AND (cm.transcript IS NULL OR length(btrim(cm.transcript))=0 OR
          cm.audio_media_id IS NULL OR asset.status NOT IN ('ready','deleted') OR
          (cm.sender='user' AND cm.transcription_status<>'completed'))))), 'Invalid conversation reply, transcript, or media');
    SELECT count(*) INTO n FROM ai_jobs j WHERE j.status IN ('queued','running','cancel_requested') AND
      ((j.job_type='start_conversation' AND j.attempt_id=m.attempt_id) OR
       (j.job_type='process_voice_turn' AND EXISTS(SELECT 1 FROM conversation_messages cm
         WHERE cm.message_id=j.message_id AND cm.conversation_session_id=m.conversation_session_id)));
    PERFORM ep_assert(n<=1, 'Only one active voice job is allowed per conversation');
    IF m.status='ended' THEN
      PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM ai_jobs j WHERE j.status IN ('queued','running') AND
        ((j.job_type='start_conversation' AND j.attempt_id=m.attempt_id) OR
         (j.job_type='process_voice_turn' AND EXISTS(SELECT 1 FROM conversation_messages cm
          WHERE cm.message_id=j.message_id AND cm.conversation_session_id=m.conversation_session_id)))),
        'Ended conversation cannot have active voice work');
    END IF;
  END LOOP;

  PERFORM ep_assert(NOT EXISTS(SELECT 1 FROM ai_jobs j WHERE eid IN (SELECT ep_exercise_ids('ai_jobs',to_jsonb(j))) AND
    (j.requested_by<>e.created_by OR
     (j.job_type='start_conversation' AND e.skill<>'speaking') OR
     (j.job_type='process_voice_turn' AND NOT EXISTS(SELECT 1 FROM conversation_messages WHERE message_id=j.message_id AND sender='user')) OR
     (j.job_type='grade_answer' AND NOT EXISTS(SELECT 1 FROM answers x JOIN questions z USING(question_id)
       WHERE x.answer_id=j.answer_id AND x.submitted_at IS NOT NULL AND z.grading_method='rubric')) OR
     (j.job_type='evaluate_attempt' AND NOT EXISTS(SELECT 1 FROM attempts WHERE attempt_id=j.attempt_id AND submitted_at IS NOT NULL)))),
    'AI job owner or target is invalid');
END $$;

CREATE FUNCTION ep_check_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE eid uuid;
BEGIN
  FOR eid IN SELECT id FROM (
      SELECT ep_exercise_ids(TG_TABLE_NAME, CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) ELSE '{}'::jsonb END) AS id
      UNION SELECT ep_exercise_ids(TG_TABLE_NAME, CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) ELSE '{}'::jsonb END) AS id
    ) affected WHERE id IS NOT NULL ORDER BY id LOOP
    PERFORM ep_validate_exercise(eid);
  END LOOP;
  RETURN NULL;
END $$;


-- Attach revision 0002 triggers.
CREATE TRIGGER trg_users_guard BEFORE INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('user_id');
CREATE CONSTRAINT TRIGGER trg_users_integrity AFTER INSERT OR UPDATE OR DELETE ON users
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_auth_sessions_guard BEFORE INSERT OR UPDATE OR DELETE ON auth_sessions
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('session_id,user_id');
CREATE CONSTRAINT TRIGGER trg_auth_sessions_integrity AFTER INSERT OR UPDATE OR DELETE ON auth_sessions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_password_reset_tokens_guard BEFORE INSERT OR UPDATE OR DELETE ON password_reset_tokens
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('reset_id,user_id');
CREATE CONSTRAINT TRIGGER trg_password_reset_tokens_integrity AFTER INSERT OR UPDATE OR DELETE ON password_reset_tokens
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_topics_guard BEFORE INSERT OR UPDATE OR DELETE ON topics
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('topic_id');
CREATE CONSTRAINT TRIGGER trg_topics_integrity AFTER INSERT OR UPDATE OR DELETE ON topics
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_ai_personas_guard BEFORE INSERT OR UPDATE OR DELETE ON ai_personas
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('persona_id');
CREATE CONSTRAINT TRIGGER trg_ai_personas_integrity AFTER INSERT OR UPDATE OR DELETE ON ai_personas
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_media_assets_guard BEFORE INSERT OR UPDATE OR DELETE ON media_assets
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('media_id,owner_user_id,purpose,storage_key');
CREATE CONSTRAINT TRIGGER trg_media_assets_integrity AFTER INSERT OR UPDATE OR DELETE ON media_assets
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_exercises_guard BEFORE INSERT OR UPDATE OR DELETE ON exercises
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('exercise_id,created_by,skill');
CREATE CONSTRAINT TRIGGER trg_exercises_integrity AFTER INSERT OR UPDATE OR DELETE ON exercises
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_writing_exercises_guard BEFORE INSERT OR UPDATE OR DELETE ON writing_exercises
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('exercise_id');
CREATE CONSTRAINT TRIGGER trg_writing_exercises_integrity AFTER INSERT OR UPDATE OR DELETE ON writing_exercises
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_reading_exercises_guard BEFORE INSERT OR UPDATE OR DELETE ON reading_exercises
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('exercise_id');
CREATE CONSTRAINT TRIGGER trg_reading_exercises_integrity AFTER INSERT OR UPDATE OR DELETE ON reading_exercises
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_listening_exercises_guard BEFORE INSERT OR UPDATE OR DELETE ON listening_exercises
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('exercise_id');
CREATE CONSTRAINT TRIGGER trg_listening_exercises_integrity AFTER INSERT OR UPDATE OR DELETE ON listening_exercises
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_speaking_exercises_guard BEFORE INSERT OR UPDATE OR DELETE ON speaking_exercises
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('exercise_id');
CREATE CONSTRAINT TRIGGER trg_speaking_exercises_integrity AFTER INSERT OR UPDATE OR DELETE ON speaking_exercises
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_attempts_guard BEFORE INSERT OR UPDATE OR DELETE ON attempts
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('attempt_id,user_id,exercise_id,attempt_number,source_attempt_id');
CREATE CONSTRAINT TRIGGER trg_attempts_integrity AFTER INSERT OR UPDATE OR DELETE ON attempts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_writing_attempts_guard BEFORE INSERT OR UPDATE OR DELETE ON writing_attempts
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('attempt_id');
CREATE CONSTRAINT TRIGGER trg_writing_attempts_integrity AFTER INSERT OR UPDATE OR DELETE ON writing_attempts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_reading_attempts_guard BEFORE INSERT OR UPDATE OR DELETE ON reading_attempts
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('attempt_id');
CREATE CONSTRAINT TRIGGER trg_reading_attempts_integrity AFTER INSERT OR UPDATE OR DELETE ON reading_attempts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_listening_attempts_guard BEFORE INSERT OR UPDATE OR DELETE ON listening_attempts
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('attempt_id');
CREATE CONSTRAINT TRIGGER trg_listening_attempts_integrity AFTER INSERT OR UPDATE OR DELETE ON listening_attempts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_questions_guard BEFORE INSERT OR UPDATE OR DELETE ON questions
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('question_id,exercise_id');
CREATE CONSTRAINT TRIGGER trg_questions_integrity AFTER INSERT OR UPDATE OR DELETE ON questions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_question_options_guard BEFORE INSERT OR UPDATE OR DELETE ON question_options
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('option_id,question_id');
CREATE CONSTRAINT TRIGGER trg_question_options_integrity AFTER INSERT OR UPDATE OR DELETE ON question_options
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_answers_guard BEFORE INSERT OR UPDATE OR DELETE ON answers
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('answer_id,attempt_id,question_id');
CREATE CONSTRAINT TRIGGER trg_answers_integrity AFTER INSERT OR UPDATE OR DELETE ON answers
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_evaluations_guard BEFORE INSERT OR UPDATE OR DELETE ON evaluations
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('evaluation_id,attempt_id');
CREATE CONSTRAINT TRIGGER trg_evaluations_integrity AFTER INSERT OR UPDATE OR DELETE ON evaluations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_criterion_results_guard BEFORE INSERT OR UPDATE OR DELETE ON criterion_results
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('criterion_result_id,evaluation_id,criterion_code');
CREATE CONSTRAINT TRIGGER trg_criterion_results_integrity AFTER INSERT OR UPDATE OR DELETE ON criterion_results
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_exercise_vocabulary_guard BEFORE INSERT OR UPDATE OR DELETE ON exercise_vocabulary
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('vocabulary_item_id,exercise_id');
CREATE CONSTRAINT TRIGGER trg_exercise_vocabulary_integrity AFTER INSERT OR UPDATE OR DELETE ON exercise_vocabulary
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_conversation_sessions_guard BEFORE INSERT OR UPDATE OR DELETE ON conversation_sessions
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('conversation_session_id,attempt_id');
CREATE CONSTRAINT TRIGGER trg_conversation_sessions_integrity AFTER INSERT OR UPDATE OR DELETE ON conversation_sessions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_conversation_messages_guard BEFORE INSERT OR UPDATE OR DELETE ON conversation_messages
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('message_id,conversation_session_id,client_message_key,sender,position,reply_to_message_id');
CREATE CONSTRAINT TRIGGER trg_conversation_messages_integrity AFTER INSERT OR UPDATE OR DELETE ON conversation_messages
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_ai_jobs_guard BEFORE INSERT OR UPDATE OR DELETE ON ai_jobs
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('job_id,requested_by,exercise_id,attempt_id,answer_id,message_id,job_type');
CREATE CONSTRAINT TRIGGER trg_ai_jobs_integrity AFTER INSERT OR UPDATE OR DELETE ON ai_jobs
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
CREATE TRIGGER trg_api_idempotency_keys_guard BEFORE INSERT OR UPDATE OR DELETE ON api_idempotency_keys
FOR EACH ROW EXECUTE FUNCTION ep_guard_write('idempotency_record_id,user_id,idempotency_key,operation,request_hash');
CREATE CONSTRAINT TRIGGER trg_api_idempotency_keys_integrity AFTER INSERT OR UPDATE OR DELETE ON api_idempotency_keys
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ep_check_write();
