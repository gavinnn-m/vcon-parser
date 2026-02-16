# vCon Email Parser

A Python library and CLI for converting email thread data into [vCon](https://vcon.dev) format.

## What's vCon?

vCon is an open standard for representing conversation data. It captures participants, message events, and analysis in a single portable document format.

## Two-Phase Architecture

This parser uses a progressive enrichment approach:

1. **Phase 1 (`generate_base`)** → vCon 0.0.1 with raw structured email data. No LLM needed.
2. **Phase 2 (`add_analysis`)** → vCon 0.0.2 with summaries, action items, topics from your LLM of choice.

This means you can store email records immediately and defer expensive AI analysis for later (or skip it entirely).

## CLI Usage

```bash
# From a JSON file
python3 vcon_generator.py email.json -o output.vcon.json

# Pipe from stdin
cat email.json | python3 vcon_generator.py > output.vcon.json

# With analysis (two-phase)
python3 vcon_generator.py email.json --analysis analysis.json -o enriched.vcon.json
```

## Library Usage

```python
from vcon_generator import VconGenerator
from datetime import datetime, timezone

# Phase 1: Structure the raw email data
gen = VconGenerator()
vcon = gen.generate_base({
    "subject": "Q4 Planning Call",
    "from": "Alice <alice@example.com>",
    "to": "Bob <bob@example.com>, Carol <carol@example.com>",
    "cc": "Dave <dave@example.com>",
    "source": "email_thread",
    "entry_date": datetime(2026, 2, 15, 14, 0, tzinfo=timezone.utc),
    "content": "Full email body text here...",
    "message_id": "<abc123@example.com>"
})

# Phase 2: Add LLM analysis later
vcon = gen.add_analysis({
    "summary": "Team aligned on Q4 priorities...",
    "action_items": [
        {"assignee": "Bob", "description": "Draft proposal by Friday"},
        {"assignee": "Carol", "description": "Schedule follow-up"}
    ],
    "key_topics": ["Q4 planning", "budget", "hiring"],
    "category": "planning",
    "source": "gpt-4"  # or whatever model you used
})

print(gen.to_json())
```

## Input Format

The input JSON should include:

### Required Fields

- `subject` (string): Email subject line
- `from` (string): Sender email address (format: `"Name <email@example.com>"` or `email@example.com`)
- `content` (string): Email body text (not required if `is_forwarded=true`)

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `to` | string | Recipients (comma-separated, same format as `from`) |
| `cc` | string | CC recipients (comma-separated) |
| `source` | string | `email_thread` or `forwarded_email` (default: `email_thread`) |
| `entry_date` | datetime/string | Email timestamp (ISO 8601 format) |
| `message_id` | string | Email Message-ID header |
| `reply_to` | string | Reply-To header |
| `in_reply_to` | string | In-Reply-To header (message ID of parent email) |
| `references` | string or list | References header (message IDs of email thread) |
| `is_forwarded` | bool | Whether this is a forwarded email |
| `user_note` | string | Forwarder's note (required if `is_forwarded=true`) |
| `original_content` | string | Original forwarded email content (required if `is_forwarded=true`) |

## Forwarded Email Support

For forwarded emails, set `is_forwarded: true` and provide both `user_note` (the forwarder's message) and `original_content` (the forwarded email body). This creates two message events in the vCon:

```json
{
    "subject": "Fwd: Budget Approval Request",
    "from": "Alice <alice@example.com>",
    "to": "Bob <bob@example.com>",
    "source": "forwarded_email",
    "is_forwarded": true,
    "user_note": "Bob, can you handle this? Seems urgent.",
    "original_content": "Hi, we need approval for the Q4 budget...",
    "entry_date": "2026-02-15T10:30:00Z",
    "message_id": "<fwd789@example.com>"
}
```

## Analysis Format

For phase 2, pass a dict with any of:

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Email thread summary |
| `action_items` | list | `[{assignee, description, due_date?}]` |
| `key_topics` | list | Topic strings |
| `key_decisions` | list | Decision strings |
| `category` | string | Classification label |
| `source` | string | Vendor/model name (e.g., "gpt-4", "claude-3") |

## Output

Standard vCon JSON with `participants`, `events`, `analysis`, and `sources` arrays. Compatible with any vCon-aware tooling.

## Error Handling

The parser validates input and raises clear `VconValidationError` exceptions for:

- Missing required fields (`subject`, `from`, `content`)
- Invalid source types (must be `email_thread` or `forwarded_email`)
- Malformed email addresses (returns None, doesn't crash)
- Missing `user_note` or `original_content` for forwarded emails

## Examples

See the `examples/` directory for:

- `email.json` - Simple email thread
- `forwarded-email.json` - Forwarded email with user note
- `analysis.json` - LLM analysis to enrich a vCon

## Authors

- Matt Gavin ([@gavinnn-m](https://github.com/gavinnn-m))
