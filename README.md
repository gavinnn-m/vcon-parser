# vCon Parser

A Python library and CLI for converting structured conversation data (emails, meetings, transcripts) into [vCon](https://vcon.dev) format.

## What's vCon?

vCon is an open standard for representing conversation data. Think of it as a structured envelope for any conversation: emails, phone calls, meetings, chat threads. It captures participants, events, and analysis in a single portable document.

## Two-Phase Architecture

This tool uses a progressive enrichment approach:

1. **Phase 1 (`generate_base`)** → vCon 0.0.1 with raw structured data. No LLM needed.
2. **Phase 2 (`add_analysis`)** → vCon 0.0.2 with summaries, action items, topics from your LLM of choice.

This means you can store conversation records immediately and defer expensive AI analysis for later (or skip it entirely).

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

# Phase 1: Structure the raw data
gen = VconGenerator()
vcon = gen.generate_base({
    "subject": "Q4 Planning Call",
    "from": "Alice <alice@example.com>",
    "to": "Bob <bob@example.com>, Carol <carol@example.com>",
    "source": "meeting_transcript",
    "entry_date": datetime(2026, 1, 15, 14, 0),
    "duration_minutes": 45,
    "content": "Full transcript text here...",
    "participants": ["Alice", "Bob", "Carol"]
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

The input JSON should include some combination of:

| Field | Type | Description |
|-------|------|-------------|
| `subject` / `title` | string | Conversation subject |
| `from` | string | Sender (email format: `"Name <email>"`) |
| `to` | string | Recipients (comma-separated) |
| `participants` | list | Participant names |
| `content` | string | Body text or transcript |
| `source` | string | `email_thread`, `meeting_transcript`, `chat`, `forwarded_email` |
| `entry_date` | datetime/string | When the conversation occurred |
| `duration_minutes` | int | For meetings |
| `is_forwarded` | bool | If it's a forwarded email |
| `user_note` | string | Forwarder's note |
| `original_content` | string | Original forwarded content |
| `message_id` | string | Email Message-ID header |

## Analysis Format

For phase 2, pass a dict with any of:

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Conversation summary |
| `action_items` | list | `[{assignee, description, due_date?}]` |
| `key_topics` | list | Topic strings |
| `key_decisions` | list | Decision strings |
| `category` | string | Classification label |
| `source` | string | Vendor/model name |

## Output

Standard vCon JSON with `participants`, `events`, `analysis`, and `sources` arrays. Compatible with any vCon-aware tooling.

## Authors

- Matt Gavin ([@gavinnn-m](https://github.com/gavinnn-m))
- Scout (AI Lab Ranger 🔭)
