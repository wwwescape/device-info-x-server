from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Device Info X Server</title>
<script>
  // Runs before first paint so there's no flash of the wrong theme.
  (function () {{
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {{
      document.documentElement.dataset.theme = saved;
    }}
  }})();
</script>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f5f5f7;
    --card-bg: #ffffff;
    --text: #1d1d1f;
    --muted: #6e6e73;
    --border: #e5e5ea;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0b0b0d;
      --card-bg: #17171a;
      --text: #f5f5f7;
      --muted: #9a9aa2;
      --border: #2c2c2e;
    }}
  }}
  :root[data-theme="light"] {{
    color-scheme: light;
    --bg: #f5f5f7;
    --card-bg: #ffffff;
    --text: #1d1d1f;
    --muted: #6e6e73;
    --border: #e5e5ea;
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --bg: #0b0b0d;
    --card-bg: #17171a;
    --text: #f5f5f7;
    --muted: #9a9aa2;
    --border: #2c2c2e;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100svh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .card {{
    position: relative;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 2.5rem 3rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  }}
  .theme-toggle {{
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 50%;
    background: transparent;
    color: var(--muted);
    font-size: 1rem;
    line-height: 1;
    cursor: pointer;
  }}
  .theme-toggle:hover {{
    color: var(--text);
    border-color: var(--muted);
  }}
  h1 {{
    margin: 0 0 1.5rem;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 0.02em;
  }}
  .status-row {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
  }}
  .dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: {dot_color};
    flex-shrink: 0;
  }}
  .dot::after {{
    content: "";
    display: block;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: {dot_color};
    animation: pulse 1.8s ease-out infinite;
  }}
  @keyframes pulse {{
    0% {{ transform: scale(1); opacity: 0.7; }}
    100% {{ transform: scale(2.8); opacity: 0; }}
  }}
  .status-text {{
    font-size: 1.4rem;
    font-weight: 600;
  }}
  .devices-row {{
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    font-size: 0.85rem;
    color: var(--muted);
  }}
  .status-list-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.5rem;
    padding: 0.3rem 0;
  }}
  .status-list-row + .status-list-row {{
    border-top: 1px solid var(--border);
  }}
  .icon-badge {{
    width: 20px;
    height: 20px;
    min-width: 20px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
    font-size: 0.75rem;
    font-weight: 700;
  }}
  .icon-badge.ok {{ background: #30d158; }}
  .icon-badge.no {{ background: #ff453a; }}
  .timestamp {{
    margin-top: 1rem;
    font-size: 0.8rem;
    color: var(--muted);
  }}
</style>
</head>
<body>
  <div class="card">
    <button class="theme-toggle" type="button" onclick="
      var current = document.documentElement.dataset.theme
        || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem('theme', next);
    " aria-label="Toggle light/dark theme">&#9680;</button>
    <h1>Device Info X Server</h1>
    <div class="status-row">
      <span class="dot"></span>
      <span class="status-text">{status_text}</span>
    </div>
    <div class="devices-row">{devices_rows}</div>
    <div class="timestamp">Last checked: {checked_at}</div>
  </div>
</body>
</html>
"""


def render_status_page(*, database_reachable: bool, registered_count: int | None, paired: bool | None) -> str:
    if database_reachable:
        status_text, dot_color = "Online", "#30d158"
    else:
        status_text, dot_color = "Degraded", "#ff453a"

    if registered_count is None or paired is None:
        devices_rows = "Pairing status unavailable"
    else:
        rows = (
            ("Partner 1 Registered", registered_count >= 1),
            ("Partner 2 Registered", registered_count >= 2),
            ("Partner 1 &amp; Partner 2 Paired", paired),
        )
        devices_rows = "".join(
            '<div class="status-list-row"><span>{label}</span>'
            '<span class="icon-badge {cls}">{glyph}</span></div>'.format(
                label=label,
                cls="ok" if ok else "no",
                glyph="&#10003;" if ok else "&#10005;",
            )
            for label, ok in rows
        )

    checked_at_ist = datetime.now(UTC).astimezone(ZoneInfo("Asia/Kolkata"))
    hour_12 = int(checked_at_ist.strftime("%I"))
    am_pm = checked_at_ist.strftime("%p").lower()
    checked_at = f"{checked_at_ist.strftime('%d/%m/%Y')} {hour_12}:{checked_at_ist.strftime('%M')}{am_pm} IST"
    return _PAGE_TEMPLATE.format(
        status_text=status_text, dot_color=dot_color, devices_rows=devices_rows, checked_at=checked_at
    )
