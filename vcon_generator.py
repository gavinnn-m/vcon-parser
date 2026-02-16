#!/usr/bin/env python3
"""
vCon Email Parser
Converts email thread data to vCon format.
See: https://vcon.dev

Supports a two-phase approach:
  1. generate_base() → vCon 0.0.1 with raw structured email data (no AI needed)
  2. add_analysis()  → vCon 0.0.2 with summaries, action items, topics (from your LLM of choice)

This lets you defer expensive LLM calls and progressively enrich conversation records.
"""

import json
import uuid
import re
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


class VconValidationError(Exception):
    """Raised when input data is invalid or missing required fields"""
    pass


class VconGenerator:
    """Generates vCon documents from email data"""

    VCON_VERSION = "0.0.1"
    VALID_SOURCE_TYPES = {"email_thread", "forwarded_email"}
    VALID_PARTICIPANT_ROLES = {"from", "to", "cc"}

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        """Reset internal vCon structure"""
        self.vcon: Dict[str, Any] = {
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

    def generate_base(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 1: Generate vCon 0.0.1 with raw structured email data (no LLM analysis).

        Args:
            data: Dict with keys:
                - subject (str, required): Email subject
                - from (str, required): Sender email address
                - to (str, optional): Recipient email addresses
                - cc (str, optional): CC email addresses
                - content (str, required): Email body text
                - source (str, optional): 'email_thread' or 'forwarded_email' (default: 'email_thread')
                - entry_date (datetime or str, optional): Email timestamp
                - message_id (str, optional): Email Message-ID header
                - is_forwarded (bool, optional): Whether this is a forwarded email
                - user_note (str, optional): Forwarder's note (for forwarded emails)
                - original_content (str, optional): Original email content (for forwarded emails)
                - reply_to (str, optional): Reply-To header
                - in_reply_to (str, optional): In-Reply-To header (message ID)
                - references (str or list, optional): References header (message IDs)

        Returns:
            vCon dict (0.0.1)

        Raises:
            VconValidationError: If required fields are missing or invalid
        """
        self._reset()
        self._validate_input(data)

        self.vcon["uuid"] = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.vcon["created_at"] = now
        self.vcon["updated_at"] = now

        # Set type from source
        source = data.get('source', 'email_thread')
        if source not in self.VALID_SOURCE_TYPES:
            raise VconValidationError(
                f"Invalid source type '{source}'. Must be one of: {', '.join(self.VALID_SOURCE_TYPES)}"
            )
        
        self.vcon["type"] = "email_forwarded" if source == "forwarded_email" else "email_thread"

        self._add_conversation_metadata(data)
        self._add_participants(data)
        self._add_events(data)
        self._add_sources(data)

        return self.vcon

    def add_analysis(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 2: Enrich an existing vCon with LLM analysis results.

        Args:
            analysis_data: Dict with optional keys:
                - summary (str): Email conversation summary
                - action_items (list): List of action items
                - category (str): Classification category
                - key_topics (list): List of key topics
                - key_decisions (list): List of key decisions
                - source (str): Vendor/model name (e.g., "gpt-4", "claude-3")

        Returns:
            Updated vCon dict (0.0.2)
        """
        self.vcon["vcon"] = "0.0.2"
        self.vcon["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._add_analysis_entries(analysis_data)
        return self.vcon

    # ── Validation ─────────────────────────────────────────────────────

    def _validate_input(self, data: Dict[str, Any]) -> None:
        """Validate required input fields"""
        required_fields = ['subject', 'from']
        
        # For non-forwarded emails, content is required
        if not data.get('is_forwarded'):
            required_fields.append('content')
        else:
            # For forwarded emails, need both user_note and original_content
            if not data.get('user_note') or not data.get('original_content'):
                raise VconValidationError(
                    "Forwarded emails require both 'user_note' and 'original_content' fields"
                )
        
        missing = [field for field in required_fields if not data.get(field)]
        if missing:
            raise VconValidationError(
                f"Missing required fields: {', '.join(missing)}"
            )
        
        # Validate source type if provided
        source = data.get('source', 'email_thread')
        if source not in self.VALID_SOURCE_TYPES:
            raise VconValidationError(
                f"Invalid source type '{source}'. Must be one of: {', '.join(self.VALID_SOURCE_TYPES)}"
            )

    # ── Conversation Metadata ──────────────────────────────────────────

    def _add_conversation_metadata(self, data: Dict[str, Any]) -> None:
        """Add high-level conversation metadata"""
        subject = data.get('subject', 'No Subject')
        self.vcon["conversation"] = {
            "subject": subject,
            "thread_topic": subject,
            "message_count": 2 if data.get('is_forwarded') else 1
        }

    # ── Participants ───────────────────────────────────────────────────

    def _add_participants(self, data: Dict[str, Any]) -> None:
        """Add participants with email addresses and roles"""
        added: set = set()
        pid = 1

        # Add sender (from field)
        from_field = data.get('from', '')
        if from_field:
            email = self._extract_email(from_field)
            name = self._extract_name(from_field) or email
            if email and email not in added:
                self.vcon["participants"].append({
                    "id": f"p{pid}",
                    "name": name,
                    "email": email,
                    "role": "from"
                })
                added.add(email)
                pid += 1

        # Add recipients (to field)
        to_field = data.get('to', '')
        if to_field:
            for email, name in self._extract_all_emails(to_field):
                if email and email not in added:
                    self.vcon["participants"].append({
                        "id": f"p{pid}",
                        "name": name,
                        "email": email,
                        "role": "to"
                    })
                    added.add(email)
                    pid += 1

        # Add CC recipients
        cc_field = data.get('cc', '')
        if cc_field:
            for email, name in self._extract_all_emails(cc_field):
                if email and email not in added:
                    self.vcon["participants"].append({
                        "id": f"p{pid}",
                        "name": name,
                        "email": email,
                        "role": "cc"
                    })
                    added.add(email)
                    pid += 1

    # ── Events ─────────────────────────────────────────────────────────

    def _add_events(self, data: Dict[str, Any]) -> None:
        """Add email message events"""
        ts = data.get('entry_date')
        if ts is None:
            ts = datetime.now(timezone.utc)
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        elif isinstance(ts, str):
            # Ensure ISO format
            try:
                parsed = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                ts = parsed.isoformat()
            except ValueError:
                # Fall back to current time if parsing fails
                ts = datetime.now(timezone.utc).isoformat()

        if data.get('is_forwarded') and data.get('user_note') and data.get('original_content'):
            # Forwarded email: two message events
            self.vcon["events"].append({
                "id": "m1",
                "type": "message",
                "channel": "email",
                "direction": "internal",
                "timestamp": ts,
                "from": "p1",
                "subject": data.get('subject', ''),
                "body": {
                    "content_type": "text/plain",
                    "text": data['user_note']
                },
                "meta": {"role": "instruction"}
            })
            
            # Clean forwarded subject (remove Fwd:, FW:, etc.)
            fwd_subject = re.sub(r'^(Fwd?|FW|Fw):\s*', '', data.get('subject', ''), flags=re.IGNORECASE)
            
            self.vcon["events"].append({
                "id": "m2",
                "type": "message",
                "channel": "email",
                "direction": "inbound",
                "timestamp": ts,
                "from": "p2" if len(self.vcon["participants"]) > 1 else "p1",
                "to": ["p1"],
                "subject": fwd_subject,
                "body": {
                    "content_type": "text/plain",
                    "text": data['original_content']
                },
                "meta": {"role": "content", "forwarded": True}
            })
        else:
            # Single message event
            content = data.get('content', '')
            if content:
                # Build recipient list
                to_ids = [p["id"] for p in self.vcon["participants"] if p["role"] in ("to", "cc")]
                
                event: Dict[str, Any] = {
                    "id": "m1",
                    "type": "message",
                    "channel": "email",
                    "direction": "inbound",
                    "timestamp": ts,
                    "from": "p1",
                    "to": to_ids[:10],  # Limit to first 10 recipients
                    "subject": data.get('subject', ''),
                    "body": {
                        "content_type": "text/plain",
                        "text": content
                    }
                }
                self.vcon["events"].append(event)

    # ── Sources ────────────────────────────────────────────────────────

    def _add_sources(self, data: Dict[str, Any]) -> None:
        """Add email source metadata including headers"""
        source_info: Dict[str, Any] = {
            "type": data.get('source', 'email_thread'),
            "message_id": data.get('message_id', '')
        }
        
        # Add email headers if present
        if data.get('reply_to'):
            source_info["reply_to"] = data['reply_to']
        
        if data.get('in_reply_to'):
            source_info["in_reply_to"] = data['in_reply_to']
        
        if data.get('references'):
            refs = data['references']
            # Handle both string and list formats
            if isinstance(refs, str):
                # Split on whitespace if it's a string
                source_info["references"] = refs.split()
            else:
                source_info["references"] = refs
        
        self.vcon["sources"].append(source_info)

    # ── Analysis ───────────────────────────────────────────────────────

    def _add_analysis_entries(self, data: Dict[str, Any]) -> None:
        """Add analysis entries to vCon"""
        vendor = data.get('source', 'llm')

        analysis_types = [
            ('summary', 'summary', 'text/plain'),
            ('category', 'category', 'text/plain'),
            ('action_items', 'action-items', 'application/json'),
            ('key_topics', 'key-topics', 'application/json'),
            ('key_decisions', 'key-decisions', 'application/json'),
        ]

        for field, atype, schema in analysis_types:
            value = data.get(field)
            if not value:
                continue
            body = value if isinstance(value, str) else json.dumps(value, indent=2)
            self.vcon["analysis"].append({
                "type": atype,
                "dialog": 0,
                "vendor": vendor,
                "product": "vcon-parser",
                "schema": schema,
                "body": body,
                "encoding": "utf-8"
            })

    # ── Email Parsing Helpers ──────────────────────────────────────────

    @staticmethod
    def _extract_email(field: str) -> Optional[str]:
        """
        Extract email address from field, handling various formats.
        
        Supports:
        - "Name <email@example.com>"
        - "<email@example.com>"
        - "email@example.com"
        - Malformed addresses (returns None)
        """
        if not field or not isinstance(field, str):
            return None
        
        field = field.strip()
        
        # Try angle bracket format first
        m = re.search(r'<([^>]+)>', field)
        if m:
            email = m.group(1).strip()
            if VconGenerator._is_valid_email(email):
                return email
        
        # Try bare email address
        m = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', field)
        if m:
            email = m.group(1).strip()
            if VconGenerator._is_valid_email(email):
                return email
        
        return None

    @staticmethod
    def _extract_name(field: str) -> Optional[str]:
        """
        Extract display name from email field.
        
        Handles:
        - "First Last <email@example.com>" → "First Last"
        - "\"Last, First\" <email@example.com>" → "Last, First"
        - "email@example.com" → None (no display name)
        """
        if not field or not isinstance(field, str):
            return None
        
        field = field.strip()
        
        # Try to extract name before <email>
        m = re.match(r'^(.+?)\s*<', field)
        if m:
            name = m.group(1).strip()
            # Remove surrounding quotes if present
            name = name.strip('"').strip("'").strip()
            if name and len(name) > 0:
                return name
        
        return None

    @staticmethod
    def _extract_all_emails(field: str) -> List[Tuple[str, str]]:
        """
        Extract all email addresses and names from a comma/semicolon-separated field.
        
        Returns list of (email, name) tuples.
        Name defaults to email if no display name found.
        """
        if not field or not isinstance(field, str):
            return []
        
        results: List[Tuple[str, str]] = []
        
        # Split on commas or semicolons, but be careful with quoted names
        # Pattern handles: "Name" <email>, Name <email>, email
        parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', field)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            email = VconGenerator._extract_email(part)
            if email:
                name = VconGenerator._extract_name(part)
                results.append((email, name or email))
        
        return results

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Basic email validation"""
        if not email or '@' not in email:
            return False
        # Simple check: has @ and at least one dot after @
        parts = email.split('@')
        if len(parts) != 2:
            return False
        local, domain = parts
        if not local or not domain or '.' not in domain:
            return False
        return True

    # ── Export ─────────────────────────────────────────────────────────

    def to_json(self, indent: int = 2) -> str:
        """Export vCon as JSON string"""
        return json.dumps(self.vcon, indent=indent, default=str)

    def to_dict(self) -> Dict[str, Any]:
        """Export vCon as dictionary"""
        return self.vcon


def generate_vcon_filename(data: Dict[str, Any]) -> str:
    """Generate a standardized filename for a vCon document."""
    entry_date = data.get('entry_date')
    if isinstance(entry_date, str):
        try:
            entry_date = datetime.fromisoformat(entry_date.replace('Z', '+00:00'))
        except ValueError:
            entry_date = datetime.now()
    elif not isinstance(entry_date, datetime):
        entry_date = datetime.now()
    
    subject = data.get('subject', 'email')
    date_str = entry_date.strftime('%Y-%m-%d')
    slug = re.sub(r'[^a-z0-9 ]', '', subject.lower())
    slug = '-'.join(slug.split())[:50]
    return f"{date_str}-{slug}.json"


def main():
    parser = argparse.ArgumentParser(
        description="vCon Email Parser - Convert email data to vCon format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s email.json
  %(prog)s email.json -o output.vcon.json
  %(prog)s email.json --analysis analysis.json -o enriched.vcon.json
  cat email.json | %(prog)s > output.vcon.json
        """
    )
    parser.add_argument("input", nargs="?", help="Input JSON file (or read from stdin)")
    parser.add_argument("--analysis", help="Analysis JSON file to merge (phase 2)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    args = parser.parse_args()

    import sys

    try:
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
            print(f"✓ Wrote {args.output}", file=sys.stderr)
        else:
            print(output)
    
    except VconValidationError as e:
        print(f"❌ Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
