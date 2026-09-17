# Public UI evaluation protocol — task 0.2

This protocol is supplied before the run. Wording, layout, component choices and
route names remain implementation decisions. Submit a JSON locator map alongside
the source artifact. The evaluator owns the workflow, fixture data and assertions;
the map only locates ordinary user-facing controls. It cannot run JavaScript,
call APIs, inject expected results or replace product behavior.

The [example map](../../../experiments/chatwoot-team-views/task-ui-map.json) shows
one valid UI. Its labels are examples, not hidden requirements.

## Map format

- `version: 2`.
- `audience_kind`: `select` for a native select (team IDs are option values and
  `0` means personal), or `menu` for a trigger plus an `audience_option` and
  `personal_option` locator. Use the menu adapter for other selection patterns.
- `prepare_create`: up to eight UI steps from the conversation screen to prepare
  the existing **status = open** query and open the save UI.
- `set_resolved`: up to eight steps inside the editor to change that query to
  **status = resolved**. The evaluator verifies actual persisted results.
- A step may be a locator key (click), or an object with `control`, `action`
  (`click`, `select`, `fill`) and `value` for select/fill. No executable steps,
  arbitrary keyboard scripts, network calls or custom assertion functions.
- `locators`: each has `by` (`css`, `role`, `label`, `placeholder`, `text`),
  `value`, optional CSS `scope`, and `role` for role locators. Names/text match
  exactly. Templates support `{view_name}`, `{team_id}`, `{team_name}`.

Required locator keys: `audience`, `name`, `save`, `save_error`, `view_heading`,
`view_link`, `edit`, `edit_name`, `edit_save`, `edit_error`, `delete`,
`delete_confirm`, `delete_cancel`, `delete_error`, `personal_link`,
`personal_heading`, and keys used by the two step lists. Menu adapters additionally
need `audience_option` and `personal_option`. If blank-name save remains enabled,
provide `validation_error` for the resulting visible validation state.

Each action must uniquely identify a control. `view_heading` locates visible
view/team identity (a common container is allowed); `view_link` locates the saved
entry. The personal equivalents omit team identity. Management locators must
identify the same real controls for every actor; readers may have no control,
a hidden control or a disabled control. A reviewer checks the map for misleading
selectors before accepting a result. Missing/ambiguous targets are reported as
protocol errors requiring investigation, not automatically declared product bugs.

Error locators identify visible failure feedback, not a permanently displayed
label. The UI need not echo the evaluator's exact error message. Independent HTTP
checks verify that the save was rejected and inputs/data were preserved.

## Fixed browser scenarios

The browser image pins Playwright 1.56.1 and Chromium 141.0.7390.37. It runs the
production build in a separate container, with a 1440 × 1000 viewport.

1. Alice creates a Support view. Blank-name validation works. A forced HTTP 422
   shows failure and preserves name/query/audience; keyboard retry succeeds.
2. Reload and a fresh login retain view/team identity and correct visible results.
3. The creator edits both name and query. A rejected update retains inputs, and
   retry persists the resolved query and expected results.
4. Bob opens it, sees only his permitted matches and has no enabled management
   controls. Restricted-inbox contact names are absent.
5. Dana opens the view with zero visible conversations and retains view identity.
6. After membership removal, Bob's reload removes the entry. Rejoining and
   reloading restores access within the same browser login.
7. An ordinary nonmember cannot discover the entry.
8. A nonmember administrator opens and edits the shared view.
9. Delete cancellation preserves it. Rejected deletion shows failure and keeps it.
10. Confirmed administrator deletion removes it after a member's reload.
    After a rejected deletion, the confirmation may remain open or be reopened.
11. Alice creates a personal view, reloads it, edits it and deletes it; Bob cannot
    discover it. Existing personal workflows are also covered by API regressions.

New audience controls need an accessible name and keyboard focus. Save, update
and delete confirmation are activated with the keyboard. Full focus order,
visual integration and localization quality are reviewed separately using the
published review rubric; passing the browser checks does not claim those human
review items have been completed.

Login and conversation rendering retain the supplied upstream conventions.
Account permissions, lifecycle, pagination and unread counts are independently
verified through API behavior. A change to this protocol requires a new task
version and rerunning comparisons; no post-submission hidden UI requirements.
