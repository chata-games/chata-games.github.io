#!/usr/bin/env python3
"""E2E: Forest Rescue — every campaign level boots and runs.

Companion to scripts/e2e_forest_rescue_pages.py (same chrome-agent plumbing,
same failure watching). While that script proves one full battle end to end,
this one walks EVERY level listed in forest-rescue/levels/campaign.json:

  per level:  navigate to <SITE>?level=<id>
              -> #gameScreen visible, #levelTitle shows the level's name
              -> engine ALIVE: within 90s the wave counter leaves
                 "Wave 1 / N", or the end overlay shows (an idle run with no
                 defenders may honestly lose during wave 1 — e.g. Sawmill
                 Clearing's wave 1 is 5 loggers against 5 hearts; a resolved
                 battle is an alive engine, a frozen HUD is not)
              -> zero watched failure events (uncaught exceptions, failed
                 network loads, console errors) and zero 4xx/5xx assets
              -> RP-vebqyv fit at the pinned 940x850 window: no page overflow,
                 every toolbar card fully on-screen (reachable), canvas and
                 canvasWrap inside the viewport

Rules (inherited from the pages smoke):
  1. Sense, act, sense again — DOM state is read back and asserted; return
     values of actions are never trusted.
  2. Wait on events, never on sleep — Page.loadEventFired via scripts/cdp-wait.py,
     DOM state via short polls. No fixed sleeps.
  3. Failure is watched everywhere — one background `attach` stream subscribes
     to Runtime.exceptionThrown, Network.loadingFailed and Runtime.consoleAPICalled
     (type error) for the whole run; any hit fails the run.
  4. Fail loudly — expected vs observed printed, failure screenshot saved, and
     the exit code is the pass/fail signal.

Usage:  FR_E2E_SITE=http://127.0.0.1:8341/ python3 scripts/e2e_forest_rescue_all_levels.py
Artifacts: /tmp/fr-all-levels-*.png, /tmp/fr-all-levels-events.jsonl
"""

import base64
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WAITER = os.path.join(HERE, "cdp-wait.py")
GAME = os.path.abspath(os.path.join(HERE, "..", "forest-rescue"))
# Target site; override to smoke-test a local server before the Pages deploy lands.
SITE = os.environ.get("FR_E2E_SITE", "https://chata-games.github.io/forest-rescue/")
EVENTS = "/tmp/fr-all-levels-events.jsonl"


def load_levels():
    """Level ids come from campaign.json; names and wave counts from the
    compiled level data the game itself loads."""
    with open(os.path.join(GAME, "levels", "campaign.json"), encoding="utf-8") as f:
        campaign = json.load(f)
    levels = []
    for entry in campaign["levels"]:
        level_id = entry["id"]
        with open(os.path.join(GAME, "levels", "compiled", f"{level_id}.json"), encoding="utf-8") as f:
            compiled = json.load(f)
        if compiled["id"] != level_id:
            raise SystemExit(f"campaign/compiled mismatch: {level_id} vs {compiled['id']}")
        levels.append({"id": level_id, "name": compiled["name"], "waves": len(compiled["waves"])})
    return levels


class Fail(Exception):
    pass


class Runner:
    def __init__(self):
        self.inst = None
        self.attach = None
        self.evfile = None
        self.wait_offset = 0  # cdp-wait chain offset
        self.scan_pos = 0  # our own scanner position in the events file
        self.step = "setup"

    # ---- chrome-agent plumbing (mirrors e2e_forest_rescue_pages.py) -------

    def sh(self, args, timeout=60):
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

    def ca(self, method, params_json):
        r = self.sh(["chrome-agent", self.inst, method, params_json])
        if r.returncode != 0:
            raise Fail(f"chrome-agent {method} failed: {r.stderr.strip()[:400]}")
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            raise Fail(f"chrome-agent {method} returned non-JSON: {r.stdout[:400]}")

    def evaluate(self, expression):
        out = self.ca("Runtime.evaluate", json.dumps({"expression": expression, "returnByValue": True}))
        if out.get("exceptionDetails"):
            raise Fail(f"page JS error in evaluate: {json.dumps(out['exceptionDetails'])[:400]}")
        return out.get("result", {}).get("value")

    def wait_event(self, method, timeout):
        r = self.sh(
            ["python3", WAITER, "--file", EVENTS, "--method", method, "--timeout", str(timeout), "--print-offset", "--from-offset", str(self.wait_offset)]
        )
        m = re.search(r"offset=(\d+)", r.stderr)
        if m:
            self.wait_offset = int(m.group(1))
        if r.returncode != 0:
            raise Fail(f"timed out waiting for {method} within {timeout}s")
        return json.loads(r.stdout)

    def js_click(self, selector):
        """Locate via DOM, act via trusted input events (press + release)."""
        pos = self.evaluate(
            f'(()=>{{const el=document.querySelector("{selector}");'
            "if(!el) return null; const r=el.getBoundingClientRect();"
            "return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};})()"
        )
        if not pos:
            raise Fail(f"js_click: {selector} not found")
        self.click(pos["x"], pos["y"])

    def click(self, x, y):
        for mtype in ("mousePressed", "mouseReleased"):
            self.ca("Input.dispatchMouseEvent", json.dumps({"type": mtype, "x": x, "y": y, "button": "left", "clickCount": 1}))

    def navigate(self, url, timeout=40):
        self.ca("Page.navigate", json.dumps({"url": url}))
        self.wait_event("Page.loadEventFired", timeout)

    def pin_viewport(self):
        """Pin the window to 940x850 (the RP-vebqyv regression size, where 8
        toolbar cards at the old min-width forced a 2296px page overflow)."""
        self.ca("Emulation.setDeviceMetricsOverride", json.dumps({"width": 940, "height": 850, "deviceScaleFactor": 1, "mobile": False}))

    def screenshot(self, tag):
        try:
            out = self.ca("Page.captureScreenshot", json.dumps({"format": "png"}))
            path = f"/tmp/fr-all-levels-{tag}.png"
            with open(path, "wb") as f:
                f.write(base64.b64decode(out["data"]))
            print(f"  screenshot: {path}")
        except Fail as e:
            print(f"  screenshot failed: {e}")

    # ---- failure watching --------------------------------------------------

    def check_events(self):
        """Scan the attach stream for failure events; fail loudly on any."""
        with open(EVENTS, encoding="utf-8") as f:
            f.seek(self.scan_pos)
            lines = f.readlines()
            self.scan_pos = f.tell()
        for line in lines:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            method = ev.get("method")
            if method == "Runtime.exceptionThrown":
                details = json.dumps(ev.get("params", {}))[:500]
                raise Fail(f"uncaught page exception: {details}")
            if method == "Network.loadingFailed":
                p = ev.get("params", {})
                # A superseded navigation aborts the in-flight document load;
                # that is a race, not a broken asset. Real failures aren't canceled.
                if p.get("canceled") or "ERR_ABORTED" in str(p.get("errorText", "")):
                    continue
                raise Fail(f"network load failed: {json.dumps(p)[:300]}")
            if method == "Runtime.consoleAPICalled" and ev.get("params", {}).get("type") == "error":
                args = [json.dumps(a.get("value", a.get("description", "?")))[:200] for a in ev["params"].get("args", [])]
                raise Fail(f"console error: {' '.join(args)}")

    def bad_resources(self):
        """4xx/5xx subresources (the classic GitHub-Pages subpath bug), favicon excluded."""
        found = self.evaluate(
            'performance.getEntriesByType("resource")'
            ".filter(e=>e.responseStatus&&e.responseStatus>=400&&!/favicon/.test(e.name))"
            ".map(e=>e.responseStatus+' '+e.name)"
        )
        return found or []

    # ---- assertions ----------------------------------------------------------

    def expect_eq(self, observed, expected, what):
        if observed != expected:
            raise Fail(f"{what}: expected {expected!r}, observed {observed!r}")

    def poll(self, expression, predicate, what, timeout=15):
        last = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            last = self.evaluate(expression)
            if predicate(last):
                return last
            time.sleep(0.5)
        raise Fail(f"timed out after {timeout}s waiting for {what}; last observed {last!r}")

    def visible(self, selector):
        return f'!document.querySelector("{selector}").classList.contains("hidden")'

    def holds(self, expression, predicate, what, seconds=3):
        """Observation window (RP-48sjgh): the predicate must hold on EVERY
        read for `seconds` seconds. This is an assertion, not a wait — any
        violating read fails immediately."""
        last = None
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            last = self.evaluate(expression)
            if not predicate(last):
                raise Fail(f"{what}: state changed during hold window; observed {last!r}")
            time.sleep(0.5)
        return last

    def gate_state(self):
        """RP-48sjgh wave gate probe: HUD wave text + Start-Wave visibility."""
        return ('(()=>({wave:document.querySelector("#waveText").textContent,'
                'startVisible:!document.querySelector("#startWaveButton").classList.contains("hidden")}))()')

    def text_of(self, selector):
        return f'document.querySelector("{selector}").textContent'

    def assert_fit(self, level_id):
        """RP-vebqyv: layout fits the pinned viewport on this level — no page
        overflow (the old 8x280px card bar forced 2296px), every toolbar card
        fully on-screen and tappable, canvas and wrap inside the window. Also
        asserts the RP-pyvp2r role line is present on every card."""
        fit = self.evaluate(
            "(()=>{const iw=window.innerWidth,ih=window.innerHeight;"
            "const sw=document.documentElement.scrollWidth;"
            "const btns=[...document.querySelectorAll('.tool-button')].map((b)=>{const r=b.getBoundingClientRect();"
            "return {text:b.textContent.slice(0,24),role:(b.querySelector('.tool-button__role')||{textContent:''}).textContent.trim(),l:r.left,t:r.top,r:r.right,b:r.bottom};});"
            "const c=document.getElementById('gameCanvas').getBoundingClientRect();"
            "const w=document.getElementById('canvasWrap').getBoundingClientRect();"
            "return {iw,ih,sw,cards:btns,canvas:{l:c.left,t:c.top,r:c.right,b:c.bottom},wrap:{l:w.left,t:w.top,r:w.right,b:w.bottom}};})()"
        )
        if not isinstance(fit, dict):
            raise Fail(f"fit probe on {level_id} returned {fit!r}")
        if fit["sw"] > fit["iw"] + 1:
            raise Fail(f"page overflows viewport on {level_id}: scrollWidth {fit['sw']} > innerWidth {fit['iw']}")
        off = [b["text"] for b in fit["cards"]
               if b["l"] < -1 or b["t"] < -1 or b["r"] > fit["iw"] + 1 or b["b"] > fit["ih"] + 1]
        if off:
            raise Fail(f"cards unreachable on {level_id} at {fit['iw']}x{fit['ih']}: {off}")
        bare = [b["text"] for b in fit["cards"] if not b.get("role")]
        if bare:
            raise Fail(f"cards missing a role line (RP-pyvp2r) on {level_id}: {bare}")
        for name, box in (("#gameCanvas", fit["canvas"]), ("#canvasWrap", fit["wrap"])):
            if box["l"] < -1 or box["t"] < -1 or box["r"] > fit["iw"] + 1 or box["b"] > fit["ih"] + 1:
                raise Fail(f"{name} exceeds viewport on {level_id} at {fit['iw']}x{fit['ih']}: {box}")
        print(f"  ok: fit at {fit['iw']}x{fit['ih']} — scrollWidth {fit['sw']}, {len(fit['cards'])} cards reachable with role lines, canvas+wrap inside viewport")

    # ---- per-level flow --------------------------------------------------------

    def play_level(self, index, level):
        level_id, name, waves = level["id"], level["name"], level["waves"]
        self.step = f"level {index + 1}/{len(LEVELS)}: {name} ({level_id})"
        print(f"[{index + 1}/{len(LEVELS)}] {name!r} via {SITE}?level={level_id}")
        self.navigate(f"{SITE}?level={level_id}")
        self.poll("document.readyState", lambda v: v == "complete", "document.readyState==complete")
        self.poll(self.visible("#gameScreen"), lambda v: v is True, "#gameScreen visible (level param entry)", timeout=30)
        self.expect_eq(self.evaluate(self.text_of("#levelTitle")), name, "level title")
        # Engine alive: HUD shows live integers and, within 90s, either the
        # wave counter leaves "Wave 1 / N" or the end overlay is genuinely
        # shown. The hidden overlay ships with static "Game Over" text in
        # index.html, so title text alone is NOT a resolution signal — the
        # #endOverlay element must have lost its "hidden" class too. An idle
        # run with no defenders may honestly lose during wave 1; a resolved
        # battle is an alive engine, a frozen HUD is not.
        self.poll(self.text_of("#manaText"), lambda v: isinstance(v, str) and v.isdigit(), "live mana value", timeout=10)
        first_wave = f"Wave 1 / {waves}"
        observed = self.evaluate(self.text_of("#waveText"))
        if observed != first_wave:
            print(f"  note: waveText already past wave 1 at first read: {observed!r}")
        # RP-48sjgh: wave 1 must hold behind a visible Start-Wave button until
        # it is pressed — no auto-advancing waves on level entry.
        gate = self.gate_state()
        self.holds(gate, lambda v: isinstance(v, dict) and v.get("wave") == first_wave and v.get("startVisible") is True,
                   f"wave 1 held behind visible Start-Wave button ({first_wave})", seconds=3)
        self.js_click("#startWaveButton")
        self.poll(gate, lambda v: isinstance(v, dict) and v.get("startVisible") is False, "#startWaveButton hidden after press")
        hud = self.poll(
            '(()=>({wave:document.querySelector("#waveText").textContent,'
            'endVisible:!document.querySelector("#endOverlay").classList.contains("hidden"),'
            'end:document.querySelector("#endTitle").textContent}))()',
            lambda v: isinstance(v, dict)
            and (
                v.get("wave") != first_wave
                or (v.get("endVisible") is True and v.get("end") in ("Victory", "Game Over"))
            ),
            f"wave counter leaves {first_wave!r} or end overlay is shown",
            timeout=90,
        )
        if hud.get("endVisible") and hud.get("wave") == first_wave:
            print(f"  note: battle resolved during wave 1 (idle run, no defenders): {hud['end']!r} — engine alive")
        bad = self.bad_resources()
        if bad:
            raise Fail(f"4xx/5xx subresources on {level_id} (Pages subpath bug?): {bad}")
        self.assert_fit(level_id)
        self.check_events()
        print(f"  ok: title {name!r}, engine alive (wave {hud['wave']!r}, end overlay visible: {hud['endVisible']}, title: {hud['end']!r}), no failures")

    # ---- lifecycle -------------------------------------------------------------

    def run(self):
        r = self.sh(["chrome-agent", "launch", "--headless"])
        if r.returncode != 0:
            raise Fail(f"chrome-agent launch failed: {r.stderr.strip()[:400]}")
        self.inst = json.loads(r.stdout)["name"]
        print(f"launched chrome instance {self.inst}")
        status = self.sh(["chrome-agent", "status"]).stdout
        if self.inst not in status:
            raise Fail(f"instance {self.inst} not listed in status after launch")
        try:
            self.evfile = open(EVENTS, "w")
            self.attach = subprocess.Popen(
                ["chrome-agent", "attach", self.inst, "+Page.loadEventFired", "+Page.frameNavigated", "+Runtime.exceptionThrown", "+Network.loadingFailed", "+Runtime.consoleAPICalled"],
                stdout=self.evfile,
                stderr=subprocess.DEVNULL,
            )
            self.pin_viewport()  # pin before any navigation so every level runs at 940x850
            for i, level in enumerate(LEVELS):
                self.play_level(i, level)
            self.screenshot("final")
            print(f"\nPASS: all {len(LEVELS)} campaign levels boot, run, and stay clean on {SITE}")
        except Fail as e:
            try:
                self.check_events()  # surface any watched failure alongside the assertion failure
                watched = None
            except Fail as watched_exc:
                watched = watched_exc
            print(f"\nFAIL at {self.step}: {e}", file=sys.stderr)
            if watched:
                print(f"watched failure also fired: {watched}", file=sys.stderr)
            self.screenshot("failure")
            sys.exit(1)
        finally:
            self.teardown()

    def teardown(self):
        if self.attach:
            self.attach.terminate()
        if self.evfile:
            self.evfile.close()
        if self.inst:
            self.sh(["chrome-agent", "stop", self.inst])
            status = self.sh(["chrome-agent", "status"]).stdout
            if self.inst in status:
                print(f"WARNING: instance {self.inst} still listed after stop", file=sys.stderr)
                sys.exit(1)
            print("teardown ok: browser stopped")


LEVELS = load_levels()

if __name__ == "__main__":
    print(f"campaign: {len(LEVELS)} levels -> " + ", ".join(f"{l['id']} ({l['name']}, {l['waves']} waves)" for l in LEVELS))
    Runner().run()
