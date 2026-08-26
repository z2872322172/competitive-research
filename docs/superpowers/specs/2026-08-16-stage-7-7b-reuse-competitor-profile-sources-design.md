# Stage 7.7B Reuse Competitor Profile Sources Design

## Goal

When users create a research task, saved competitor profile sources are reused automatically so repeated competitor research starts from known official URLs.

## Scope

- Match `ResearchTaskCreate.competitors` against `CompetitorProfile.name` in the default workspace.
- Merge matched profile source URLs into task `scope.source_preferences` without removing user-provided sources.
- Store structured reuse metadata in `scope.competitor_profile_reuse`.
- Show reused source hints on the frontend confirmation page.

## Backend Design

`create_task()` will call a small helper that loads matching competitor profiles and extracts their `source_urls`. The resulting URLs are appended to the existing `source_preferences` list with stable de-duplication.

The scope stores:

```json
{
  "competitor_profile_reuse": [
    {
      "profile_id": "comp_x",
      "name": "Cursor",
      "source_count": 2,
      "source_urls": [
        {"label": "Pricing", "url": "https://cursor.com/pricing", "source_type": "official"}
      ]
    }
  ]
}
```

This keeps the workflow compatible with existing collection code, which already accepts source preferences as URL strings.

## Frontend Design

The confirmation page already shows research settings. Stage 7.7B adds a compact "竞品库复用来源" section when `taskDetail.task.scope.competitor_profile_reuse` exists. A helper converts raw scope data into display rows so malformed or missing data produces an empty list.

## Testing

- Backend API contract test creates a competitor profile, creates a matching task, and asserts merged source preferences and structured reuse metadata.
- Frontend helper test verifies display rows and empty fallback behavior.
