"""Transactional email dispatch via Resend.

`send_email` is a safe no-op when RESEND_API_KEY is missing so the rest of the
app keeps working in dev. Non-blocking via asyncio.to_thread.
"""
import os
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("mailer")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()

_resend = None
if RESEND_API_KEY:
    try:
        import resend as _resend_mod
        _resend_mod.api_key = RESEND_API_KEY
        _resend = _resend_mod
    except Exception as e:
        logger.warning(f"resend SDK failed to init: {e}")
        _resend = None


async def send_email(*, to: str, subject: str, html: str) -> dict:
    """Send a single transactional email. Returns {"sent": bool, "id": str|None, "reason": str}."""
    if not _resend:
        logger.info(f"[mailer:noop] would send to={to} subject={subject!r}")
        return {"sent": False, "id": None, "reason": "RESEND_API_KEY not configured"}
    params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
    try:
        result = await asyncio.to_thread(_resend.Emails.send, params)
        return {"sent": True, "id": (result or {}).get("id"), "reason": "ok"}
    except Exception as e:
        logger.warning(f"resend send failed to={to}: {e}")
        return {"sent": False, "id": None, "reason": str(e)[:200]}


def rate_nudge_html(*, talent_name: str, current_rate: float, mid: int,
                    low: int, high: int, drift_pct: float, direction: str,
                    dashboard_url: str, rationale: Optional[str] = "") -> str:
    """Render the rate nudge HTML email body. Inline CSS only (email-client safe)."""
    tone_color = "#0B7A4B" if direction == "raise" else "#B03A2E"
    arrow = "↑" if direction == "raise" else "↓"
    first = (talent_name or "there").split(" ")[0]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>Rate check-in from Job Atlas</title></head>
<body style="margin:0;padding:0;background:#FAF9F6;font-family:Georgia,serif;color:#0B1B2B;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FAF9F6;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border:1px solid #E5E7EB;border-radius:2px;">
        <tr><td style="padding:32px 32px 8px 32px;">
          <p style="margin:0 0 4px 0;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;color:#C79A3B;text-transform:uppercase;">Monthly rate nudge</p>
          <h1 style="margin:0;font-size:26px;line-height:1.15;letter-spacing:-.01em;">Hey {first} — your rate needs a look.</h1>
        </td></tr>
        <tr><td style="padding:16px 32px 0 32px;">
          <p style="margin:0 0 12px 0;font-size:15px;line-height:1.55;color:#333;">
            Your current listed rate is <strong>${current_rate:.0f}/hr</strong>. Based on your skills,
            experience and location, Job Atlas&apos;s market model suggests a range of
            <strong>${low}–${high}/hr</strong> (mid <strong>${mid}/hr</strong>) — a drift of
            <span style="color:{tone_color};font-weight:700;">{arrow} {abs(drift_pct):.0f}%</span>.
          </p>
          {f'<p style="margin:0 0 12px 0;font-size:14px;color:#666;font-style:italic;">{rationale}</p>' if rationale else ''}
          <p style="margin:0 0 24px 0;font-size:14px;color:#555;">
            {"Bumping your rate keeps you competitive on quality perception. Buyers here value structured pricing." if direction == "raise" else "You're above market. That can be intentional — but be ready to justify with portfolio and reviews."}
          </p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
            <tr><td style="background:#0B1B2B;border-radius:2px;">
              <a href="{dashboard_url}" style="display:inline-block;padding:14px 28px;color:#FFFFFF;text-decoration:none;font-weight:700;font-size:14px;font-family:Arial,sans-serif;">
                Review &amp; apply ${mid}/hr →
              </a>
            </td></tr>
          </table>
          <p style="margin:0 0 12px 0;font-size:12px;color:#999;font-family:'Courier New',monospace;letter-spacing:1px;text-transform:uppercase;">
            Sent by Job Atlas · operated by Denkoit Softech Pvt. Ltd.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
