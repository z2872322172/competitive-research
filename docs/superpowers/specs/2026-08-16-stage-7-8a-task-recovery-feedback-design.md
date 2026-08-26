# Stage 7.8A Task Recovery Feedback Design

## Goal

When a task fails, is canceled, or is resumable, the UI should show a clear recovery hint and the right primary action.

## Scope

- Add a tested frontend helper that derives recovery feedback from task status and latest run status.
- Show the feedback in the task detail panel.
- Keep backend retry/resume/cancel behavior unchanged.

## Feedback Rules

- Failed task + failed latest run: show resume-first guidance and expose `resume`.
- Failed task without failed latest run: show retry guidance and expose `retry`.
- Canceled task: show restart guidance and expose `retry`.
- Running or queued task: show cancel guidance and expose `cancel`.
- Completed task: no recovery feedback.

## Testing

Node tests cover failed, canceled, active, and completed states.
