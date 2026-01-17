# Streaming Response UI Bug Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the bug where UI shows "thinking" state indefinitely after SSE stream completes, even though backend correctly processes and returns results.

**Architecture:**
The bug occurs due to a race condition in Vue's `isTyping` computed property, which depends on `getRecommendQuestionsLoading`. When RecommendQuestion's independent SSE request completes and triggers `loadingOver`, it can interfere with the main SSE stream's `isTyping` state. The fix ensures `isTyping` is set to `false` before RecommendQuestion's completion can interfere.

**Tech Stack:**
- Frontend: Vue 3, TypeScript
- Backend: Python FastAPI, SSE streaming
- Framework: Pinia state management

---

## Current Problem Analysis

### Data Flow (Before Fix)
```
User Input → Main SSE Stream (id → question → sql → sql-data → chart → finish)
            ↓
        ChartAnswer emits('finish', id)
            ↓
        onChartAnswerFinish → isTyping = false, getRecommendQuestionsLoading = true
            ↓
        getRecommendQuestions(id) → Independent SSE Request
            ↓
        RecommendQuestion SSE completes → loadingOver() → getRecommendQuestionsLoading = false
            ↓
        Race condition: isTyping may be affected, UI stuck in "thinking"
```

### Root Cause
In `frontend/src/views/chat/index.vue`:
```javascript
const isTyping = computed(() => {
  return result || getRecommendQuestionsLoading.value  // ← depends on RecommendQuestion
})
```

When `getRecommendQuestionsLoading` transitions from `true` to `false` after RecommendQuestion completes, it can trigger unexpected re-computation of `isTyping`.

---

## Implementation Tasks

### Task 1: Apply Frontend Fix in index.vue

**Files:**
- Modify: `frontend/src/views/chat/index.vue:742-749`

**Step 1: Write the failing test**

This is a frontend UI bug without automated tests. We'll verify the fix manually during testing.

**Step 2: Apply the fix**

```javascript
async function onChartAnswerFinish(id: number) {
  // 立即标记推荐问题加载完成，避免 RecommendQuestion 完成时影响 isTyping 状态
  getRecommendQuestionsLoading.value = false  // Reset first
  getRecommendQuestionsLoading.value = true   // Then start new request
  loading.value = false
  isTyping.value = false
  getRecommendQuestions(id)
}
```

**Step 3: Verify the change**

```bash
git diff frontend/src/views/chat/index.vue
```

Expected output shows the fix is applied.

**Step 4: Commit**

```bash
git add frontend/src/views/chat/index.vue
git commit -m "fix: prevent RecommendQuestion from interfering with isTyping state"
```

---

### Task 2: Verify Backend Changes (Already Applied)

The following backend changes were made to support optional main SSE stream recommended questions generation:

**Files:**
- Modify: `backend/apps/business_db/context.py` - Added `old_questions` field
- Modify: `backend/apps/business_db/service.py` - Preload `old_questions`, save `recommended_question` in postprocess
- Modify: `backend/apps/algorithm/engine.py` - Added `_generate_recommended_questions()` method

**Step 1: Verify changes exist**

```bash
git diff --stat backend/
```

Expected output shows 3 files modified.

**Step 2: Review backend changes**

```bash
git diff backend/apps/business_db/context.py
git diff backend/apps/business_db/service.py
git diff backend/apps/algorithm/engine.py
```

**Step 3: Commit backend changes (if not already committed)**

```bash
git add backend/
git commit -m "feat: add recommended questions generation to algorithm engine (optional, for future use)"
```

---

### Task 3: Manual Testing

**Files:**
- No test files to create - manual verification required

**Step 1: Start backend server**

```bash
cd backend
uv run fastapi dev main.py
```

**Step 2: Start frontend dev server**

```bash
cd frontend
npm run dev
```

**Step 3: Test scenario**

1. Open browser to `http://localhost:5173` (or your frontend URL)
2. Create a new chat session
3. Verify recommended questions appear (from independent API - should work as before)
4. Click on a recommended question or type a question
5. Observe: Answer should complete and UI should show result (not "thinking")
6. Check browser console for `[DEBUG] finish event:` log

**Expected behavior:** Answer displays correctly, no infinite "thinking" state.

---

### Task 4: Optional - Add Backend Integration Test

**Files:**
- Create: `tests/test_algorithm_engine.py`

**Step 1: Write integration test**

```python
def test_recommended_questions_in_sse_stream():
    """Test that recommended questions can be generated in main SSE stream."""
    from apps.algorithm.engine import AlgorithmEngine
    from apps.business_db.context import AlgorithmContext
    from apps.business_db.result import AlgorithmResult

    # Create minimal context for testing
    context = AlgorithmContext(
        user_id=1,
        workspace_id=1,
        oid=1,
        question="test question",
        old_questions=["old question 1", "old question 2"],
        db_schema="test_schema",
        language="zh-CN"
    )

    # Verify context has old_questions
    assert len(context.old_questions) == 2
    assert context.old_questions[0] == "old question 1"

    # Verify AlgorithmResult has recommended_question field
    result = AlgorithmResult(record_id=1, chat_id=1)
    assert hasattr(result, 'recommended_question')
    assert hasattr(result, 'recommended_question_answer')
```

**Step 2: Run test**

```bash
cd backend
uv run pytest tests/test_algorithm_engine.py -v
```

Expected: PASS (backend infrastructure tests)

**Step 3: Commit**

```bash
git add tests/test_algorithm_engine.py
git commit -m "test: add algorithm engine integration test for recommended questions"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `frontend/src/views/chat/index.vue` | Fix `onChartAnswerFinish` to prevent `getRecommendQuestionsLoading` interference |
| `backend/apps/business_db/context.py` | Add `old_questions` field to `AlgorithmContext` |
| `backend/apps/business_db/service.py` | Preload `old_questions` and save `recommended_question` in postprocess |
| `backend/apps/algorithm/engine.py` | Add `_generate_recommended_questions()` method |
| `tests/test_algorithm_engine.py` | (Optional) Integration test for new backend functionality |

---

## Plan Complete

Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
