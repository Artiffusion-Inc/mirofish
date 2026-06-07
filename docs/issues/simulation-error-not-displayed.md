# Issue: Frontend Does Not Display Error Message When Simulation Fails [Fixed]

**Status**: Fixed
**Fix Date**: 2026-01-05
**Fix File**: `frontend/src/components/Step3Simulation.vue`

## Problem Description

When the backend simulation run fails, the error message only appears in the backend logs. The frontend interface shows no error indication, leaving the user unaware that the simulation has failed.

## Reproduction Steps

1. Start the frontend and backend services
2. Create a project and upload a document
3. Build the GraphRAG (succeeds)
4. Click "Start Simulation"
5. Simulation fails due to missing dependencies

## Actual Behavior

**Backend log shows the error:**
```
Error: Missing dependency No module named 'camel'
Please install first: pip install oasis-ai camel-ai
```

**Frontend behavior:**
- No error notification of any kind
- The interface may show a "Simulating" status but never updates
- The user has no way to know the simulation has failed

## Expected Behavior

- The frontend should display a clear error notification (e.g., Toast/Modal)
- The error message should include the specific reason
- The user should see a suggestion to "install dependencies"

## Technical Analysis

### Possible Causes

1. **API response not returning errors correctly**
   - The backend may only print logs but return an empty response or a non-standard error format

2. **Frontend not handling error responses**
   - The catch block of the API call may be empty or unimplemented

3. **WebSocket/SSE connection issues**
   - If real-time communication is used, error events may not be listened for

### Files to Check

| Location | File | What to Check |
|----------|------|---------------|
| Backend | `app/routes/*.py` | API error response format |
| Backend | `app/services/simulation*.py` | Exception handling logic |
| Frontend | `src/api/*.ts` | API call error handling |
| Frontend | `src/components/*Simulation*.tsx` | Error state display |

## Suggested Fix Approaches

### Approach A: Unified Error Response Format

```python
# Backend API returns a standard error format
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({
        "success": False,
        "error": {
            "code": "SIMULATION_FAILED",
            "message": str(e),
            "suggestion": get_suggestion(e)
        }
    }), 500
```

### Approach B: Frontend Global Error Handling

```typescript
// Frontend axios interceptor
api.interceptors.response.use(
  response => response,
  error => {
    const message = error.response?.data?.error?.message || 'Unknown error';
    toast.error(message);
    return Promise.reject(error);
  }
);
```

## Related Background

This issue was discovered while testing the Graphiti localization plan. Due to a neo4j version conflict between `camel-ai` and `graphiti-core`:
- `camel-ai` requires `neo4j==5.23.0`
- `graphiti-core` requires `neo4j>=5.26.0`

This caused the simulation feature to fail, but the error was not communicated to the user.

## Priority

**Medium** - Affects user experience, but does not affect core functionality

## Labels

- `bug`
- `frontend`
- `error-handling`
- `ux`

---

## Fix Details

### Root Cause

The `fetchRunStatus()` function in `Step3Simulation.vue` only checked for `completed` and `stopped` statuses, **completely ignoring the `failed` status**:

```javascript
// Original code (line 512)
const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped'
// Missing handling for runner_status === 'failed'
```

### Fix Applied

Added detection of the `failed` status in `fetchRunStatus()` (lines 511-519):

```javascript
// Detect whether the simulation has failed
if (data.runner_status === 'failed') {
  const errorMsg = data.error || 'Simulation run failed'
  addLog(`✗ Simulation failed: ${errorMsg}`)
  phase.value = 2  // Enter completion phase (allow viewing logs/retry)
  stopPolling()
  emit('update-status', 'error')
  return
}
```

### Fix Effect

- The frontend log panel displays the error message: `✗ Simulation failed: Process exit code: 1, error: ...No module named 'camel'...`
- The status indicator changes to the error state (red)
- The user can clearly see the reason for the simulation failure
