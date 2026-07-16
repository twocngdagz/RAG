"""Drive the ChatGPT web app from code, to use a Project as a generation backend.

Codex proved the mechanism (claim the ChatGPT tab, send a prompt, read the JSON),
but its browser control is bound to the Codex desktop-app runtime and isn't
scriptable from the CLI. This is a self-contained replacement: Playwright drives
Chrome directly, so it needs neither Codex, AppleScript, nor a CDP debug port on
your default profile (which current Chrome blocks).

Approach: a *dedicated, persistent* Chrome profile (its own user-data-dir), using
your installed Chrome via channel="chrome". You log into ChatGPT once in that
profile; because Projects live on the account, that profile then has the same
"English Learning App" project and "Learning Item Enrichment" chat. After that the
driver reuses the session forever.

Usage:
  # 1. one-time: open headed and log in to ChatGPT in the automation profile
  python chatgpt_browser_driver.py login

  # 2. send a prompt to a specific chat and print the reply
  python chatgpt_browser_driver.py send \
      --chat-url "https://chatgpt.com/g/.../project" --prompt "consummate"

The reply-complete detection watches the stop/send button and then requires the
assistant text to stop changing -- the robust pattern for scraping a streaming UI.
"""

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

DEFAULT_PROFILE = ".chatgpt-profile"
CHATGPT_HOME = "https://chatgpt.com/"

# Selectors are kept tolerant: ChatGPT's DOM shifts, so each role tries several.
COMPOSER = "#prompt-textarea, div[contenteditable='true'], textarea[data-testid='prompt-textarea']"
SEND_BTN = "[data-testid='send-button'], button[aria-label*='Send' i]"
STOP_BTN = "[data-testid='stop-button'], button[aria-label*='Stop' i]"
ASSISTANT = "[data-message-author-role='assistant']"
USER = "[data-message-author-role='user']"

# Plan/usage-limit notices ChatGPT shows when an account gets restricted. Checked
# on failure paths so a rate-limited batch stops immediately instead of burning
# more attempts against a capped account.
RESTRICTION_RE = re.compile(
    r"(you.{0,5}ve? reached (your|the)\b.{0,40}\blimit"
    r"|message limit reached"
    r"|usage (cap|limit)"
    r"|too many requests"
    r"|reached our limit"
    r"|you.{0,5}ve? hit (your|the)\b.{0,40}\blimit"
    r"|try again (later|after|in)"
    r"|upgrade to (plus|pro|go) to continue)",
    re.IGNORECASE,
)


class ChatGPTDriver:
    def __init__(self, profile_dir: str, *, headless: bool):
        self._profile = str(Path(profile_dir).resolve())
        self._headless = headless
        self._pw = None
        self._ctx = None
        self.page = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        # Persistent context = a real, reusable Chrome profile. channel="chrome"
        # uses the system Chrome (no bundled-browser download).
        self._ctx = self._pw.chromium.launch_persistent_context(
            self._profile,
            channel="chrome",
            headless=self._headless,
            args=["--no-first-run", "--no-default-browser-check"],
            viewport=None,
        )
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *_exc):
        for closer in (self._ctx, self._pw):
            try:
                closer and (closer.close() if self._ctx is closer else closer.stop())
            except Exception:
                pass

    def is_logged_in(self) -> bool:
        self.page.goto(CHATGPT_HOME, wait_until="domcontentloaded")
        try:
            self.page.wait_for_selector(COMPOSER, timeout=8000)
            return True
        except PWTimeout:
            return False

    def wait_for_login(self, timeout_s: int = 300) -> None:
        """Headed: block until the composer appears (user has logged in)."""
        print("Log into ChatGPT in the opened window… waiting for the composer.")
        self.page.goto(CHATGPT_HOME, wait_until="domcontentloaded")
        self.page.wait_for_selector(COMPOSER, timeout=timeout_s * 1000)
        print("Logged in. Session saved to the profile.")

    def restriction_notice(self) -> str | None:
        """Scan the visible page for a plan/rate-limit notice. Returns the matching
        line (what ChatGPT actually said) or None. Call on failure paths only —
        lesson content on a successful page could contain look-alike phrases."""
        try:
            text = self.page.evaluate("() => document.body.innerText") or ""
        except Exception:
            return None
        for line in text.splitlines():
            if RESTRICTION_RE.search(line):
                return line.strip()
        return None

    def _wait_until(self, predicate, seconds: float) -> bool:
        """Poll predicate() until true or the budget elapses. Swallows errors so a
        transient DOM detach during navigation doesn't abort the wait."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                if predicate():
                    return True
            except Exception:
                pass
            time.sleep(0.3)
        return False

    def _send_prompt(self, prompt: str) -> None:
        """Type the prompt and actually submit it, verifying a new user turn
        appears. ChatGPT's composer is a ProseMirror contenteditable: fill() often
        fails to update React state (leaving the send button disabled and Enter a
        no-op), so we use real key events and retry until the message registers."""
        before_user = self.page.locator(USER).count()
        for attempt in range(1, 4):
            composer = self.page.wait_for_selector(COMPOSER, timeout=15000)
            composer.click()
            self.page.keyboard.press("Meta+A")
            self.page.keyboard.press("Backspace")
            self.page.keyboard.insert_text(prompt)  # dispatches input events

            # Wait for the send control to enable (proof the state updated), click
            # it, and fall back to Enter if it never enables.
            clicked = False
            if self._wait_until(
                lambda: (b := self.page.query_selector(SEND_BTN)) is not None and b.is_enabled(),
                6,
            ):
                self.page.query_selector(SEND_BTN).click()
                clicked = True
            if not clicked:
                self.page.keyboard.press("Enter")

            if self._wait_until(lambda: self.page.locator(USER).count() > before_user, 8):
                return
            print(f"  send attempt {attempt} did not register; retrying…")
        raise RuntimeError("Could not submit the prompt (no user turn appeared after 3 attempts).")

    def send_and_wait(self, chat_url: str, prompt: str, *, timeout_s: int = 180) -> str:
        self.page.goto(chat_url, wait_until="domcontentloaded")
        self.page.wait_for_selector(COMPOSER, timeout=30000)
        before = self.page.locator(ASSISTANT).count()
        self._send_prompt(prompt)
        return self._await_reply(before_count=before, timeout_s=timeout_s)

    def _await_reply(self, *, before_count: int, timeout_s: int) -> str:
        deadline = time.time() + timeout_s
        started = time.time()
        # 1. wait for a new assistant turn (or the stop button) to appear.
        while time.time() < deadline:
            if self.page.locator(ASSISTANT).count() > before_count or self.page.query_selector(STOP_BTN):
                break
            time.sleep(0.4)

        # 2. wait for generation to finish: no stop button AND text stable.
        last_text, stable, last_log = "", 0, 0.0
        while time.time() < deadline:
            generating = self.page.query_selector(STOP_BTN) is not None
            nodes = self.page.locator(ASSISTANT)
            text = nodes.nth(nodes.count() - 1).inner_text() if nodes.count() else ""
            if not generating and text and text == last_text:
                stable += 1
                if stable >= 3:  # ~1.5s unchanged after streaming stopped
                    return text.strip()
            else:
                stable = 0
            # heartbeat so a long generation never looks like a hang.
            now = time.time()
            if now - last_log >= 15:
                print(f"  …waiting for reply ({int(now - started)}s, {len(text)} chars, "
                      f"{'generating' if generating else 'settling'})")
                last_log = now
            last_text = text
            time.sleep(0.5)

        raise TimeoutError(f"No stable reply within {timeout_s}s (got {len(last_text)} chars).")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Drive the ChatGPT web app as a backend.")
    p.add_argument("command", choices=["login", "check", "send"])
    p.add_argument("--profile-dir", default=DEFAULT_PROFILE)
    p.add_argument("--chat-url", help="URL of the target chat/project (for send).")
    p.add_argument("--prompt", help="Prompt text (for send).")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--headless", action="store_true", help="Run without a visible window.")
    p.add_argument("--out", help="Write the reply to this file instead of stdout.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    # login/check must be headed so you can sign in and see it.
    headless = args.headless and args.command == "send"

    with ChatGPTDriver(args.profile_dir, headless=headless) as d:
        if args.command == "login":
            d.wait_for_login(timeout_s=max(args.timeout, 300))
            return 0
        if args.command == "check":
            print("logged_in" if d.is_logged_in() else "not_logged_in")
            return 0
        # send
        if not args.chat_url or not args.prompt:
            print("send requires --chat-url and --prompt", file=sys.stderr)
            return 2
        reply = d.send_and_wait(args.chat_url, args.prompt, timeout_s=args.timeout)
        if args.out:
            Path(args.out).write_text(reply, encoding="utf-8")
            print(f"reply written to {args.out} ({len(reply)} chars)")
        else:
            print(reply)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
