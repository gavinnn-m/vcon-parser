#!/usr/bin/env python3
"""
vCon Generator
Converts structured conversation data (emails, meetings, transcripts) to vCon format.
See: https://vcon.dev

Supports a two-phase approach:
  1. generate_base() → vCon 0.0.1 with raw structured data (no AI needed)
  2. add_analysis()  → vCon 0.0.2 with summaries, action items, topics (from your LLM of choice)

This lets you defer expensive LLM calls and progressively enrich conversation records.
"""

import json
import uuid
import re
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path


class VconGenerator:
    """Generates vCon documents from parsed conversation data"""

    VCON_VERSION = "0.0.1"

    def __init__(self):
        self._reset()

    def _reset(self):
        self.vcon = {
            "vcon": self.VCON_VERSION,
            "uuid": None,
            "type": None,
            "created_at": None,
            "updated_at": None,
            "conversation": {},
            "participants": [],
            "events": [],
            "analysis": [],
            "attachments": [],
            "sources": []
        }

    def generate_base(self, data: Dict) -> Dict:
        """
        Phase 1: Generate vCon 0.0.1 with raw structured data (no LLM analysis).

        Args:
            data: Dict with keys like subject, from, to, content, participants,
                  source ('email_thread', 'meeting_transcript', 'chat', etc.),
                  entry_date (datetime), is_forwarded, user_note, original_content, etc.

        Returns:
            vCon dict (0.0.1)
        """
        self._reset()
        self.vcon["uuid"] = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.vcon["created_at"] = now
        self.vcon["updated_at"] = now

        # Infer type from source
        source = data.get('source', 'email_thread')
        type_map = {
            'meeting_transcript': 'meeting_transcript',
            'otter_meeting': 'meeting_transcript',
            'forwarded_email': 'email_forwarded',
            'email_thread': 'email_thread',
            'chat': 'chat',
        }
        self.vcon["type"] = type_map.get(source, 'email_thread')

        self._add_conversation_metadata(data)
        self._add_participants(data)
        self._add_events(data)
        self._add_sources(data)

        return self.vcon

    def add_analysis(self, analysis_data: Dict) -> Dict:
        """
        Phase 2: Enrich an existing vCon with LLM analysis results.

        Args:
            analysis_data: Dict with optional keys: summary, action_items, category,
                           key_topics, key_decisions, source (vendor name)

        Returns:
            Updated vCon dict (0.0.2)
        """
        self.vcon["vcon"] = "0.0.2"
        self.vcon["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._add_analysis_entries(analysis_data)
        return self.vcon

    # ── Conversation Metadata ──────────────────────────────────────────

    def _add_conversation_metadata(self, data: Dict):
        subject = data.get('subject', data.get('title', 'No Subject'))
        self.vcon["conversation"] = {
            "subject": subject,
            "thread_topic": subject,
            "message_count": 2 if data.get('is_forwarded') else 1
        }

    # ── Participants ───────────────────────────────────────────────────

    def _add_participants(self, data: Dict):
        added = set()
        pid = 1

        # From field
        from_field = data.get('from', '')
        if from_field:
            email = self._extract_email(from_field)
            name = self._extract_name(from_field) or email
            if name and name not in added:
                self.vcon["participants"].append(
                    {"id": f"p{pid}", "name": name, "email": email, "role": "from"})
                added.add(name)
                pid += 1

        # To field
        to_field = data.get('to', '')
        if to_field:
            for email, name in self._extract_all_emails(to_field):
                if name and name not in added:
                    self.vcon["participants"].append(
                        {"id": f"p{pid}", "name": name, "email": email, "role": "to"})
                    added.add(name)
                    pid += 1

        # Explicit participants list
        for p in data.get('participants', []):
            if p and p not in added:
                self.vcon["participants"].append(
                    {"id": f"p{pid}", "name": p, "email": None, "role": "participant"})
                added.add(p)
                pid += 1

    # ── Events ─────────────────────────────────────────────────────────

    def _add_events(self, data: Dict):
        ts = data.get('entry_date', datetime.now(timezone.utc))
        if isinstance(ts, datetime):
            ts = ts.isoformat()

        if data.get('is_forwarded') and data.get('user_note') and data.get('original_content'):
            # Forwarded email: two message events
            self.vcon["events"].append({
                "id": "m1", "type": "message", "channel": "email",
                "direction": "internal", "timestamp": ts,
                "from": "p1",
                "subject": data.get('subject', ''),
                "body": {"content_type": "text/plain", "text": data['user_note']},
                "meta": {"role": "instruction"}
            })
            self.vcon["events"].append({
                "id": "m2", "type": "message", "channel": "email",
                "direction": "inbound", "timestamp": ts,
                "from": "p2" if len(self.vcon["participants"]) > 1 else "p1",
                "to": ["p1"],
                "subject": re.sub(r'^(Fwd?|FW):\s*', '', data.get('subject', '')),
                "body": {"content_type": "text/plain", "text": data['original_content']},
                "meta": {"role": "content", "forwarded": True}
            })
        else:
            content = data.get('content', '')
            if content:
                channel = "meeting" if 'meeting' in data.get('source', '') else "email"
                event = {
                    "id": "m1", "type": "message", "channel": channel,
                    "direction": "inbound", "timestamp": ts,
                    "from": "p1",
                    "to": [f"p{i}" for i in range(2, min(len(self.vcon["participants"]) + 1, 6))],
                    "subject": data.get('subject', data.get('title', '')),
                    "body": {"content_type": "text/plain", "text": content}
                }
                if data.get('duration_minutes'):
                    event["duration_seconds"] = data['duration_minutes'] * 60
                self.vcon["events"].append(event)

    # ── Sources ────────────────────────────────────────────────────────

    def _add_sources(self, data: Dict):
        self.vcon["sources"].append({
            "type": data.get('source', 'email_thread'),
            "message_id": data.get('message_id', '')
        })

    # ── Analysis ───────────────────────────────────────────────────────

    def _add_analysis_entries(self, data: Dict):
        vendor = data.get('source', 'llm')

        for field, atype, schema in [
            ('summary',       'summary',       'text/plain'),
            ('category',      'category',      'text/plain'),
            ('action_items',  'action-items',  'application/json'),
            ('key_topics',    'key-topics',    'application/json'),
            ('key_decisions', 'key-decisions', 'application/json'),
        ]:
            value = data.get(field)
            if not value:
                continue
            body = value if isinstance(value, str) else json.dumps(value, indent=2)
            self.vcon["analysis"].append({
                "type": atype, "dialog": 0, "vendor": vendor,
                "product": "vcon-parser",
                "schema": schema, "body": body, "encoding": "utf-8"
            })

    # ── Email Parsing Helpers ──────────────────────────────────────────

    @staticmethod
    def _extract_email(field: str) -> Optional[str]:
        m = re.search(r'<([^>]+)>|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', field)
        return (m.group(1) or m.group(2)) if m else None

    @staticmethod
    def _extract_name(field: str) -> Optional[str]:
        m = re.match(r'^(.+?)\s*<', field)
        if m:
            name = m.group(1).strip('"').strip()
            if name and len(name) > 1:
                return name
        return None

    @staticmethod
    def _extract_all_emails(field: str) -> List[tuple]:
        results = []
        pattern = r'(?:"?([^"<]+)"?\s*)?<([^>]+)>|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        for m in re.finditer(pattern, field):
            name = (m.group(1) or '').strip()
            email = m.group(2) or m.group(3)
            if email:
                results.append((email, name or email))
        return results

    # ── Export ─────────────────────────────────────────────────────────

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.vcon, indent=indent, default=str)

    def to_dict(self) -> Dict:
        return self.vcon


def generate_vcon_filename(data: Dict) -> str:
    """Generate a standardized filename for a vCon document."""
    entry_date = data.get('entry_date', datetime.now())
    title = data.get('title', data.get('subject', 'unknown'))
    date_str = entry_date.strftime('%Y-%m-%d')
    slug = re.sub(r'[^a-z0-9 ]', '', title.lower())
    slug = '-'.join(slug.split())[:50]
    return f"{date_str}-{slug}.json"


def main():
    parser = argparse.ArgumentParser(description="Generate vCon from JSON input")
    parser.add_argument("input", nargs="?", help="Input JSON file (or stdin)")
    parser.add_argument("--analysis", help="Analysis JSON file to merge (phase 2)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    args = parser.parse_args()

    import sys

    # Read input
    if args.input:
        with open(args.input) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    gen = VconGenerator()
    vcon = gen.generate_base(data)

    # Optionally add analysis
    if args.analysis:
        with open(args.analysis) as f:
            analysis = json.load(f)
        vcon = gen.add_analysis(analysis)

    output = gen.to_json()
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
