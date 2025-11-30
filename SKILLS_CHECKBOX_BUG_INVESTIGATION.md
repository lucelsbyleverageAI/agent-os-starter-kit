# Skills Checkbox "Select All" Infinite Loop Bug Investigation

**Date**: 2025-11-28
**Status**: UNRESOLVED
**Severity**: High - Blocks agent creation workflow

## Summary

Clicking "Select All" or "Unselect All" on the skills checkbox in the Create Agent dialog causes a React infinite loop error: "Maximum update depth exceeded".

## Error Details

```
Runtime Error: Maximum update depth exceeded. This can happen when a component
repeatedly calls setState inside componentWillUpdate or componentDidUpdate.
React limits the number of nested updates to prevent infinite loops.
```

Stack trace shows the loop happening through:
- `Checkbox` (Radix UI)
- `ConfigFieldSkills`
- `agent-form.tsx` (Controller render)
- `CreateAgentFormContent`
- `CreateAgentDialog`
- `AlertDialogOverlay` (Radix UI)

## Environment

- Next.js 15.5.4 (Webpack)
- React 19
- react-hook-form with Controller
- Radix UI Checkbox

## Root Cause Analysis

The investigation identified multiple contributing factors:

### 1. Dual State Sources (Original Issue)
The original `ConfigFieldSkills` component managed state from two sources:
- External props (`value`/`setValue`) from react-hook-form Controller
- Internal Zustand store (`useConfigStore`)

This created complexity with `isExternallyManaged` flag and conditional state reads.

### 2. Memoization Creating Stale Closures
```tsx
const selectedSkills = useMemo(() => defaults?.skills || [], [defaults?.skills]);
const selectedSkillIds = useMemo(() => selectedSkills.map((s) => s.skill_id), [selectedSkills]);
```

These memoized values were used in `useCallback` dependencies, creating potential stale closure issues.

### 3. Guard Mechanism Failure
A `useRef` guard was added to prevent re-entry:
```tsx
const isUpdatingRef = useRef(false);

const handleSelectAll = useCallback((checked: boolean) => {
  if (isUpdatingRef.current) return;
  isUpdatingRef.current = true;
  // ... update logic
  requestAnimationFrame(() => {
    isUpdatingRef.current = false;
  });
}, [...]);
```

**Why it failed**: When the parent component re-renders, react-hook-form's Controller creates a NEW `onChange` function. This causes `useCallback` to create a NEW `handleSelectAll` with a fresh `isUpdatingRef`. The guard on the new instance is always `false`.

### 4. Unstable Effect Dependencies
In `create-agent-dialog.tsx`:
```tsx
useEffect(() => {
  setFormIsDirty(form.formState.isDirty);
}, [form.formState.isDirty, setFormIsDirty]);
```

This effect fires on every form state change, updating parent state, causing cascading re-renders.

### 5. Auto-populate Effect with Unstable Dependencies
```tsx
useEffect(() => {
  // ... auto-populate all skills
}, [loading, skillsLoading, availableSkills, skillsConfigurations]);
```

`availableSkills` array has a new reference on every render from `useSkills()` hook.

## Attempted Fixes (All Failed)

### Attempt 1: Add useRef Guard
Added `isUpdatingRef` to prevent re-entry during state updates.

**Result**: Failed - Guard is per-component-instance and gets reset when new callback instances are created.

### Attempt 2: Use requestAnimationFrame for Guard Reset
Changed from `queueMicrotask` to `requestAnimationFrame` to allow more time for renders to complete.

**Result**: Failed - Same fundamental issue with guard being per-instance.

### Attempt 3: Module-level Guard
Proposed using a module-level variable instead of useRef.

**Result**: Not implemented - Decided to try simpler approach first.

### Attempt 4: Simplify to Match ConfigToolkitSelector Pattern
Completely rewrote `ConfigFieldSkills` to follow the proven pattern from `ConfigToolkitSelector`:
- Removed all guards and refs
- Removed memoization of selection state
- Read directly from props each render
- Simple handler functions

**Result**: Failed - Individual skill toggles worked, but Select All still caused infinite loop.

### Attempt 5: Fix formIsDirty Effect
Changed:
```tsx
useEffect(() => {
  setFormIsDirty(form.formState.isDirty);
}, [form.formState.isDirty, setFormIsDirty]);
```
To:
```tsx
const isDirty = form.formState.isDirty;
useEffect(() => {
  setFormIsDirty(isDirty);
}, [isDirty, setFormIsDirty]);
```

**Result**: Partial success - Individual toggles started working.

### Attempt 6: Stabilize Auto-populate Effect Dependencies
Changed from array dependencies to primitive values:
```tsx
const skillsCount = availableSkills.length;
const hasSkillsConfig = skillsConfigurations && skillsConfigurations.length > 0;
useEffect(() => {
  // ...
}, [loading, skillsLoading, skillsCount, hasSkillsConfig]);
```

**Result**: Partial success - Combined with Attempt 5, individual toggles work.

### Attempt 7: Add Early Returns to handleSelectAll
Added early returns when nothing would change:
```tsx
if (toAdd.length === 0) return;
// and
if (newSkills.length === currentSkills.length) return;
```

**Result**: Failed - Select All still causes infinite loop.

## Current State

- **Individual skill toggles**: WORKING
- **Select All / Unselect All**: BROKEN (infinite loop)

## Key Observation

The `ConfigToolkitSelector` component handles "select all tools in a toolkit" without any issues. It follows this pattern:
1. Fully controlled via props
2. Reads directly from props each render
3. Simple onChange call
4. No guards or special handling needed

The skills component now follows the same pattern, yet still fails. This suggests the issue may be:
1. Something specific to how the parent components (`CreateAgentFormContent` / `CreateAgentDialog`) handle the state update
2. A difference in how react-hook-form handles the skills field vs tools field
3. A timing issue with multiple skills being added at once vs one tool at a time
4. Possible React 19 / Next.js 15 regression with Radix Checkbox

## Files Involved

1. `apps/web/src/features/chat/components/configuration-sidebar/config-field-skills.tsx`
2. `apps/web/src/features/agents/components/create-edit-agent-dialogs/create-agent-dialog.tsx`
3. `apps/web/src/features/agents/components/create-edit-agent-dialogs/agent-form.tsx`
4. `apps/web/src/components/ui/checkbox.tsx`
5. `apps/web/src/features/skills/hooks/use-skills.ts`

## Comparison: ConfigToolkitSelector vs ConfigFieldSkills

| Aspect | ConfigToolkitSelector | ConfigFieldSkills |
|--------|----------------------|-------------------|
| Props | `value`, `onChange` | `value`, `setValue` |
| State source | Single (props) | Single (props) - after fix |
| Select All | Works | Broken |
| Individual toggle | Works | Works |
| Parent | ConfigurationSidebar | CreateAgentFormContent |
| Form library | react-hook-form Controller | react-hook-form Controller |

## Next Steps to Investigate

1. **Compare Controller usage**: Check if there's a difference in how Controller is configured between tools and skills
2. **Check Radix Checkbox version**: Possible regression or React 19 incompatibility
3. **Add console logging**: Trace exactly what's happening during the Select All flow
4. **Bisect the issue**: Try rendering ConfigFieldSkills outside of CreateAgentDialog to isolate
5. **Check if issue exists in ConfigToolkitSelector**: Try a "select all toolkits" feature to see if it also breaks

## Reproduction Steps

1. Navigate to Agents page
2. Click "Create Agent" button
3. Select any agent template
4. Go to "Skills" tab
5. Click the "Select All" checkbox
6. Observe infinite loop error

## Workaround

Currently none. Users must select skills individually, which works.
