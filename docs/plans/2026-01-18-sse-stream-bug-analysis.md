# SSE Stream Bug Analysis and Fix Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the bug where UI shows "thinking" state indefinitely after SSE stream completes, even though backend correctly processes and returns results.

**Architecture:** Analyze the race condition in SSE stream processing where `finally` block sets `_loading.value = false` before `finish` event handler completes, causing `onChatStop` to be triggered unexpectedly.

**Tech Stack:**
- Frontend: Vue 3, TypeScript, SSE streaming
- Backend: Python FastAPI, SSE streaming
- Issue: Race condition in async event handling

---

## Bug Root Cause Analysis

### SSE Stream Processing Flow (Before Fix)

```
Backend SSE Stream:
  id → question → sql → sql-data → chart → finish

Frontend ChartAnswer.vue sendMessage():
  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      _loading.value = false  // ← PROBLEM: Runs BEFORE finish event is processed!
      break
    }
    // Process events...
    case 'finish':
      currentRecord.isTyping = false
      emits('finish', currentRecord.id)  // → onChartAnswerFinish
  }
} finally {
  _loading.value = false
}
```

### The Race Condition

When the SSE stream ends (`done = true`), the following sequence occurs:

1. **Before `done` is returned:**
   - SSE stream yields `finish` event: `data: {"type":"finish"}\n\n`
   - Frontend receives and parses `finish` event
   - `emits('finish', id)` → `onChartAnswerFinish` called

2. **When `reader.read()` returns `done = true`:**
   - `finally` block runs IMMEDIATELY (synchronously)
   - `_loading.value = false` executes
   - `onChatStop` is called (from RecommendQuestion or other sources)

3. **Race:**
   - `finally` sets `_loading = false` BEFORE `onChartAnswerFinish` completes
   - This can trigger `onChatStop` in certain scenarios
   - `onChatStop` resets `isTyping.value = false`
   - But there's a race with the computed property updates

### Why This Happens

The `finally` block is synchronous and runs immediately when `done = true`, before the async `finish` event handler has fully completed and triggered all necessary state updates.

### Key Code Locations

| File | Lines | Issue |
|------|-------|-------|
| `frontend/src/views/chat/answer/ChartAnswer.vue` | 119-129, 253-255 | `finally` sets `_loading = false` before `finish` handler completes |
| `frontend/src/views/chat/index.vue` | 740-748 | `onChartAnswerFinish` handler |
| `frontend/src/views/chat/index.vue` | 761-764 | `onChatStop` handler |

---

## Implementation Tasks

### Task 1: Fix the Race Condition in ChartAnswer.vue

**Files:**
- Modify: `frontend/src/views/chat/answer/ChartAnswer.vue:253-255`

**Step 1: Write the failing test**

This is a frontend UI bug. Manual verification will be used.

**Step 2: Apply the fix**

Remove the `_loading.value = false` from the `finally` block, since it's already set in two places:
1. When `done = true` (line 127)
2. In `onChartAnswerFinish` (via `loading.value = false`)

```javascript
// Current code (BUGGY):
} finally {
  _loading.value = false
}

// Fixed code:
}
```

**Step 3: Verify the change**

```bash
git diff frontend/src/views/chat/answer/ChartAnswer.vue
```

Expected: The `finally { _loading.value = false }` line is removed.

**Step 4: Commit**

```bash
git add frontend/src/views/chat/answer/ChartAnswer.vue
git commit -m "fix: remove duplicate _loading reset causing race condition"
```

---

### Task 2: Verify Frontend Fix is Still Applied

**Files:**
- Modify: `frontend/src/views/chat/index.vue:742-749`

**Step 1: Verify the fix exists**

```bash
git diff frontend/src/views/chat/index.vue
```

Expected output should show:
```javascript
async function onChartAnswerFinish(id: number) {
  // 立即标记推荐问题加载完成，避免 RecommendQuestion 完成时影响 isTyping 状态
  getRecommendQuestionsLoading.value = false
  getRecommendQuestionsLoading.value = true
  loading.value = false
  isTyping.value = false
  getRecommendQuestions(id)
}
```

**Step 2: If not applied, apply the fix**

```javascript
async function onChartAnswerFinish(id: number) {
  // 立即标记推荐问题加载完成，避免 RecommendQuestion 完成时影响 isTyping 状态
  getRecommendQuestionsLoading.value = false
  getRecommendQuestionsLoading.value = true
  loading.value = false
  isTyping.value = false
  getRecommendQuestions(id)
}
```

**Step 3: Commit**

```bash
git add frontend/src/views/chat/index.vue
git commit -m "fix: prevent RecommendQuestion from interfering with isTyping state"
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

**Step 3: Test the fix**

1. Open browser to `http://localhost:5173` (or your frontend URL)
2. Create a new chat session
3. Verify recommended questions appear
4. Click on a recommended question or type a question
5. **Observe:**
   - Answer should complete and UI should show result
   - The "thinking" spinner should disappear
   - No infinite loading state
6. Check browser console for `[DEBUG] finish event:` log

**Expected behavior:** Answer displays correctly, no infinite "thinking" state, `onChatStop` is NOT triggered repeatedly.

---

## Summary of Changes

| File | Change |
|------|--------|
| `frontend/src/views/chat/answer/ChartAnswer.vue` | Remove duplicate `_loading.value = false` from `finally` block |
| `frontend/src/views/chat/index.vue` | Fix `onChartAnswerFinish` to prevent `getRecommendQuestionsLoading` interference |

---

## Plan Complete

**Plan saved to:** `docs/plans/2026-01-18-sse-stream-bug-analysis.md`

Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
