#!/usr/bin/env python3
"""Exercise ProofMatch W2 inside an already-open, explicitly selected macOS Safari window.

Uses Safari's Apple Events JavaScript bridge; does NOT open a user's existing tabs,
enable browser remote automation, use credentials, or connect to external providers.
Run the loopback-only demo first and give this script the *task-created* window ID:

  python3 solutions/espoo-proofmatch/safari-e2e.py \
    --window-id 12345 --url http://127.0.0.1:4197/

This tests real Safari DOM execution and interaction handlers, not physical iPhone,
VoiceOver speech, keyboard HID, visual quality or a production consent workflow.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from urllib.parse import urlparse


def evaluate(window_id: int, url: str, js: str) -> dict:
    # The URL/window guard is deliberately rechecked before *every* mutation.
    script = (
        'tell application "Safari"\n'
        f'set targetWindow to first window whose id is {window_id}\n'
        f'if (URL of current tab of targetWindow) is not {json.dumps(url)} then '
        'error "ProofMatch QA window origin/navigation mismatch"\n'
        'return do JavaScript '
        + json.dumps("JSON.stringify((() => {" + js + "})())", ensure_ascii=False)
        + ' in current tab of targetWindow\n'
        'end tell'
    )
    process = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    if process.returncode:
        raise RuntimeError("Safari Apple Events refused QA: " + process.stderr.strip()[:600])
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Safari returned non-JSON data: {process.stdout[:500]!r}") from exc


def check(label: str, got: dict, *, expected: dict) -> None:
    mismatches = {k: (got.get(k), v) for k, v in expected.items() if got.get(k) != v}
    if mismatches:
        raise AssertionError(f"{label}: {mismatches}; actual={got}")
    print(f"PASS {label}: {json.dumps(got, ensure_ascii=False, sort_keys=True)}")


def run(window_id: int, url: str) -> None:
    def js(body: str) -> dict:
        result = evaluate(window_id, url, body)
        if result.get("error"):
            raise AssertionError("Browser error: " + str(result["error"]))
        return result

    base = js("""
      document.querySelector('#reset').click();
      document.querySelector('button[data-candidate="mira"]').click();
      const people = [...document.querySelectorAll('button[data-candidate]')];
      return {
        ready: document.readyState === 'complete',
        candidates: people.map(x => x.dataset.candidate),
        renVisible: people.some(x => x.dataset.candidate === 'ren' && x.textContent.includes('No portfolio')),
        personScores: document.querySelectorAll('#candidates .score').length,
        horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
        noBookingClaim: document.body.textContent.includes('SIMULATED'),
        heading: document.querySelector('h1').innerText.replace(/\\s+/g, ' ').trim(),
        selected: document.querySelector('button[data-candidate][aria-pressed="true"]')?.dataset.candidate,
      };
    """)
    check("initial desktop Safari", base, expected={
        "ready": True,
        "candidates": ["mira", "devon", "jules", "ren", "ari"],
        "renVisible": True,
        "personScores": 0,
        "horizontalOverflow": False,
        "noBookingClaim": True,
        "heading": "Less polish. More possibility.",
        "selected": "mira",
    })

    transferred = js("""
      document.querySelector('button[data-candidate="ari"]').click();
      const text = document.querySelector('#detail').textContent;
      return {selected: document.querySelector('button[aria-pressed="true"]').dataset.candidate,
              related: text.includes('typescript → javascript'),
              disclosed: text.includes('not externally verified'),
              noScore: !document.querySelector('.candidate .score')};
    """)
    check("transferable skill conversation", transferred, expected={
        "selected": "ari", "related": True, "disclosed": True, "noScore": True,
    })

    no_portfolio = js("""
      document.querySelector('button[data-candidate="ren"]').click();
      return {selected: document.querySelector('button[aria-pressed="true"]').dataset.candidate,
              noPortfolio: document.querySelector('#detail').textContent.includes('No portfolio supplied'),
              people: document.querySelectorAll('button[data-candidate]').length,
              slotUnavailable: !document.querySelector('#slot')};
    """)
    check("no-portfolio inclusion", no_portfolio, expected={
        "selected": "ren", "noPortfolio": True, "people": 5, "slotUnavailable": True,
    })

    role_changed = js("""
      const role = document.querySelector('#role');
      role.value = 'host'; role.dispatchEvent(new Event('change', {bubbles: true}));
      return {role: role.value,
              people: document.querySelectorAll('button[data-candidate]').length,
              required: document.querySelector('#role-skills').textContent.includes('Facilitation')};
    """)
    check("alternate employer role", role_changed, expected={
        "role": "host", "people": 5, "required": True,
    })

    pending = js("""
      const role = document.querySelector('#role');
      role.value = 'repair'; role.dispatchEvent(new Event('change', {bubbles: true}));
      document.querySelector('button[data-candidate="mira"]').click();
      document.querySelector('#proposal-form button[type="submit"]').click();
      return {count: document.querySelectorAll('#meeting-list article').length,
              pending: document.querySelector('#meeting-list article')?.textContent.includes('PENDING'),
              candidateAccept: !!document.querySelector('#meeting-list [data-actor="candidate"][data-action="accept"]'),
              employerCancel: !!document.querySelector('#meeting-list [data-actor="employer"][data-action="cancel"]'),
              errorVisible: !document.querySelector('#form-error').hidden};
    """)
    check("employer proposed, candidate pending", pending, expected={
        "count": 1, "pending": True, "candidateAccept": True,
        "employerCancel": True, "errorVisible": False,
    })

    accepted = js("""
      document.querySelector('#meeting-list [data-actor="candidate"][data-action="accept"]').click();
      return {accepted: document.querySelector('#meeting-list article')?.textContent.includes('ACCEPTED'),
              cannotAcceptTwice: !document.querySelector('#meeting-list [data-action="accept"]'),
              stillCancelable: !!document.querySelector('#meeting-list [data-actor="employer"][data-action="cancel"]')};
    """)
    check("separate candidate acceptance", accepted, expected={
        "accepted": True, "cannotAcceptTwice": True, "stillCancelable": True,
    })

    cancelled = js("""
      document.querySelector('#meeting-list [data-actor="employer"][data-action="cancel"]').click();
      return {cancelled: document.querySelector('#meeting-list article')?.textContent.includes('CANCELLED'),
              slotReleased: !!document.querySelector('#slot'),
              errorHidden: document.querySelector('#meeting-error').hidden};
    """)
    check("employer cancellation releases slot", cancelled, expected={
        "cancelled": True, "slotReleased": True, "errorHidden": True,
    })

    declined = js("""
      document.querySelector('#proposal-form button[type="submit"]').click();
      document.querySelector('#meeting-list article:last-child [data-actor="candidate"][data-action="decline"]').click();
      return {count: document.querySelectorAll('#meeting-list article').length,
              declined: document.querySelector('#meeting-list article:last-child')?.textContent.includes('DECLINED'),
              slotReleased: !!document.querySelector('#slot')};
    """)
    check("candidate decline releases slot", declined, expected={
        "count": 2, "declined": True, "slotReleased": True,
    })

    final = js("""
      document.querySelector('#reset').click();
      return {empty: document.querySelector('#meeting-list').textContent.includes('No proposals yet'),
              people: document.querySelectorAll('button[data-candidate]').length,
              title: document.title,
              url: location.href};
    """)
    check("reset and no navigation", final, expected={
        "empty": True, "people": 5, "title": "ProofMatch — Make room for real potential", "url": url,
    })
    print("SAFARI_DOM_FLOW_PASS: nine checked user-journey checkpoints, synthetic only")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-id", type=int, required=True)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("QA may only target explicitly supplied loopback HTTP URLs")
    if args.window_id < 1:
        parser.error("window-id must be an existing positive Safari task-window ID")
    try:
        run(args.window_id, args.url)
    except (AssertionError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"SAFARI_QA_FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
