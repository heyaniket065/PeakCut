"""Builds the public pages of PeakCut for Netlify, into the folder `dist/`.

    python3 deploy/netlify_build.py

Netlify can show web pages but cannot run PeakCut itself: clipping needs Python, ffmpeg, a 480 MB speech model
and jobs that run for many minutes. So Netlify shows the home page, the legal pages and the pictures, and:

Sign-in is off by default, the same as the server (PEAKCUT_ACCOUNTS): the "Sign in" and "Sign up" buttons
become "Open PeakCut" and go straight into the app, and /login and /signup lead there too. With
PEAKCUT_ACCOUNTS=1 the pages are left as they are.

- if PEAKCUT_APP_URL is set (the address of a server running PeakCut, for example https://app.example.com),
  sign-in, sign-up and the app are passed through to that server, so people never leave this address;
- if it is not set, those addresses show a short page saying the app is not connected yet.

Only Python's own standard library is used, so nothing needs installing. Settings are the same as the server's:
PEAKCUT_PUBLIC_URL, PEAKCUT_CONTACT_EMAIL, PEAKCUT_LEGAL_NAME, PEAKCUT_LEGAL_COUNTRY.
"""
import html
import os
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = ROOT / "dist"

# the addresses that need the real server (sign-in, the app, its data and its files)
APP_PATHS = ["/api/*", "/app", "/app/*", "/admin", "/admin/*", "/auth/*", "/oauth/*", "/media/*", "/pub/*",
             "/login", "/signup", "/reset", "/healthz"]
NOT_CONNECTED = ["/app", "/app/*", "/login", "/signup", "/reset", "/admin", "/admin/*"]

# with sign-in off: every "sign in" or "sign up" link opens the app instead
NO_SIGN_IN = [
    ('<a class="signin" href="/login" data-auth="in">Sign in</a>', ''),
    ('href="/signup" data-auth="up">Sign up</a>', 'href="/app" data-auth="up">Open PeakCut</a>'),
    ('href="/signup" data-auth="up2"', 'href="/app" data-auth="up2"'),
    ('<a class="fcta" href="/signup">Sign up</a>', '<a class="fcta" href="/app">Open PeakCut</a>'),
    ('<li><a href="/signup">Create an account</a></li><li><a href="/login">Sign in</a></li><li><a href="/reset">Reset password</a></li>',
     '<li><a href="/app">Open PeakCut</a></li>'),
    ('location.href = signedIn ? "/app" : "/signup";', 'location.href = "/app";'),
]


def no_sign_in(page: str) -> str:
    for old, new in NO_SIGN_IN:
        page = page.replace(old, new)
    return page

LEGAL = {
    "privacy": ("Privacy Policy", "How PeakCut collects, uses and protects your data, including Google user data, cookies and your privacy rights."),
    "terms": ("Terms of Service", "The terms for using PeakCut, the AI clipping tool for streams and videos: accounts, availability and liability."),
    "acceptable-use": ("Acceptable Use Policy", "What you may and may not do with PeakCut, the AI stream clipping tool."),
}


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def main():
    # Netlify sets URL to the site's main address; PEAKCUT_PUBLIC_URL wins when it is set
    site = (env("PEAKCUT_PUBLIC_URL") or env("URL") or "http://localhost:8888").rstrip("/")
    app_url = env("PEAKCUT_APP_URL").rstrip("/")
    accounts = env("PEAKCUT_ACCOUNTS", "0") == "1"
    finish = (lambda page: page) if accounts else no_sign_in

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()

    # pictures, videos and scripts, at the same addresses the server uses
    shutil.copytree(WEB / "brand", OUT / "brand")
    (OUT / "assets").mkdir()
    for js in WEB.glob("*.js"):
        shutil.copy2(js, OUT / "assets" / js.name)

    (OUT / "index.html").write_text(finish((WEB / "landing.html").read_text(encoding="utf-8").replace("{{SITE}}", site)),
                                    encoding="utf-8")

    contact = env("PEAKCUT_CONTACT_EMAIL")
    who = (f'<a href="mailto:{html.escape(contact)}">{html.escape(contact)}</a>' if contact
           else "the contact details on our website")
    name = html.escape(env("PEAKCUT_LEGAL_NAME") or "PeakCut")
    country = env("PEAKCUT_LEGAL_COUNTRY")
    law = (f"the laws of {html.escape(country)}" if country
           else "the laws of the country where PeakCut's operator is established")
    legal = (WEB / "legal.html").read_text(encoding="utf-8")
    for page, (title, desc) in LEGAL.items():
        out = legal
        for k, v in {"{{CONTACT}}": who, "{{PAGE}}": page, "{{PAGE_PATH}}": page, "{{SITE}}": html.escape(site),
                     "{{NAME}}": name, "{{LAW}}": law, "{{TITLE}}": title, "{{DESC}}": desc}.items():
            out = out.replace(k, v)
        (OUT / f"{page}.html").write_text(finish(out), encoding="utf-8")

    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /api/\nDisallow: /auth/\n"
                                    f"Disallow: /reset\nDisallow: /media/\n\nSitemap: {site}/sitemap.xml\n")
    day = time.strftime("%Y-%m-%d")
    pages = [("/", "1.0", "weekly"), ("/terms", "0.3", "yearly"), ("/privacy", "0.3", "yearly"),
             ("/acceptable-use", "0.2", "yearly")]
    if app_url and accounts:
        pages += [("/signup", "0.8", "monthly"), ("/login", "0.4", "monthly")]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{site}{u}</loc><lastmod>{day}</lastmod><changefreq>{c}</changefreq>"
                  f"<priority>{p}</priority></url>" for u, p, c in pages) + "</urlset>")

    rules = ["/favicon.ico  /brand/favicon.svg  301"]
    if not accounts:
        # nothing to sign in to: straight into the app
        rules += [f"{p}  /app  302!" for p in ("/login", "/signup", "/reset")]
    if app_url:
        # passed through, not sent away: the address bar stays on this site and sign-in cookies keep working
        rules += [f"{p}  {app_url}{p.replace('*', ':splat')}  200!" for p in APP_PATHS]
    else:
        (OUT / "not-connected.html").write_text(NOT_CONNECTED_PAGE, encoding="utf-8")
        # the home page asks "who is signed in?"; answer "nobody" instead of an error
        (OUT / "api").mkdir()
        (OUT / "api" / "me.json").write_text('{"user": null}')
        rules += ["/api/auth/me  /api/me.json  200"]
        rules += [f"{p}  /not-connected.html  200" for p in NOT_CONNECTED]
    (OUT / "_redirects").write_text("\n".join(rules) + "\n")

    print(f"Built {OUT} for {site}" + (f", app passed through to {app_url}" if app_url else ", app not connected"))


NOT_CONNECTED_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>PeakCut is not connected yet</title>
<link rel="icon" type="image/svg+xml" href="/brand/favicon.svg">
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F7F4F1;color:#211813;
       font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
  main{max-width:460px;margin:24px;padding:32px;background:#fff;border:1px solid #EEE8E4;border-radius:16px}
  img{height:30px}
  h1{font-size:22px;margin:20px 0 8px}
  p{color:#6D6159;margin:0 0 20px}
  a.btn{display:inline-block;padding:10px 18px;border-radius:12px;background:#FF8B33;color:#2A1A12;
        text-decoration:none;font-weight:600}
  a.btn:hover{background:#FF9A4C}
</style>
</head>
<body>
<main>
  <img src="/brand/logo.svg" alt="PeakCut">
  <h1>The app is not connected yet</h1>
  <p>This site shows PeakCut's pages, but the app that makes the clips runs on a separate server that has
     not been connected yet. Please check back soon.</p>
  <a class="btn" href="/">Back to the home page</a>
</main>
</body>
</html>
"""

if __name__ == "__main__":
    main()
