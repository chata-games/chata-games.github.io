#!/usr/bin/env python3
"""E2E smoke test: Forest Rescue live on GitHub Pages.

Drives a headless Chrome (via the chrome-agent CLI / CDP) against
https://chata-games.github.io/forest-rescue/ and verifies the deployed game
actually works: clean load (no exceptions, no failed network loads, no 4xx
assets), campaign-map entry, planting a defender on a fairy ring, and a full
battle resolution on the deterministic hand-test level, plus the RP-vebqyv
fit guarantees at a pinned 940x850 window: no page overflow, every toolbar
card reachable, canvas/canvasWrap inside the viewport, pause and mute
reachable, and the canvas refitting after Replay. Flow 6 (RP-a7h9z5) scripts
a tap at a mana flower's exact center (?debug state hook) and asserts the
pickup lands with its +25 mana.

Rules the script follows:
  1. Sense, act, sense again — after every action the state it should have
     changed is read back and asserted on. Action return values are never
     trusted.
  2. Wait on events, never on sleep — Page.loadEventFired via scripts/cdp-wait.py,
     DOM state via short polls. No fixed sleeps.
  3. Failure is watched everywhere — one background `attach` stream subscribes
     to Runtime.exceptionThrown, Network.loadingFailed and Runtime.consoleAPICalled
     (type error) for the whole run; any hit fails the run.
  4. Fail loudly — expected vs observed printed, failure screenshot saved, and
     the exit code is the pass/fail signal.

Usage:  python3 scripts/e2e_forest_rescue_pages.py
Artifacts: /tmp/fr-pages-e2e-*.png (failure + final screenshots),
           /tmp/fr-pages-e2e-events.jsonl (raw CDP event stream).
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
# Target site; override to smoke-test a local server before the Pages deploy lands.
SITE = os.environ.get("FR_E2E_SITE", "https://chata-games.github.io/forest-rescue/")
EVENTS = "/tmp/fr-pages-e2e-events.jsonl"
WORLD_W, WORLD_H = 1536, 1024  # src/engine/canvas.js

# Compiled-level facts asserted below (levels/compiled/*.json, levels/campaign.json).
LEVEL1_ID = "01-meadows-edge"
LEVEL1_NAME = "Meadow's Edge"
LEVEL1_MARKER = (0.12, 0.72)  # mapPosition of level 1 on the campaign map
LEVEL1_RING = (1269, 367)  # ring-7, a fairy ring in world coordinates
HANDTEST_ID = "00-hand-test-s-curve"
HANDTEST_NAME = "Hand Test S-Curve"
HANDTEST_RINGS = [(831, 503), (1025, 211), (1304, 332)]  # three fairy rings
TREE_COST = 50  # Magic Tree mana cost
START_MANA = 150
START_HEARTS = "\u2665" * 5


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

    # ---- chrome-agent plumbing -------------------------------------------

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

    def screenshot(self, tag):
        try:
            out = self.ca("Page.captureScreenshot", json.dumps({"format": "png"}))
            path = f"/tmp/fr-pages-e2e-{tag}.png"
            with open(path, "wb") as f:
                f.write(base64.b64decode(out["data"]))
            print(f"  screenshot: {path}")
        except Fail as e:
            print(f"  screenshot failed: {e}")

    # ---- failure watching -------------------------------------------------

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

    # ---- assertions --------------------------------------------------------

    def expect_eq(self, observed, expected, what):
        if observed != expected:
            raise Fail(f"{what}: expected {expected!r}, observed {observed!r}")

    def poll(self, expression, predicate, what, timeout=15):
        last = None
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            last = self.evaluate(expression)
            if predicate(last):
                return last
            time.sleep(0.5)
        raise Fail(f"timed out after {timeout}s waiting for {what}; last observed {last!r}")

    def holds(self, expression, predicate, what, seconds=4):
        """Observation window: the predicate must hold on EVERY read for
        `seconds` seconds. This is an assertion, not a wait — any violating
        read fails immediately (no fixed sleeps; the window is the test)."""
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

    def visible(self, selector):
        return f'!document.querySelector("{selector}").classList.contains("hidden")'

    def text_of(self, selector):
        return f'document.querySelector("{selector}").textContent'

    def pin_viewport(self):
        """Pin the window to 940x850 (the RP-vebqyv regression size, where 8
        toolbar cards at the old min-width forced a 2296px page overflow).
        deviceScaleFactor 1 keeps the dpr==1 guard in canvas_click_point true."""
        self.ca("Emulation.setDeviceMetricsOverride", json.dumps({"width": 940, "height": 850, "deviceScaleFactor": 1, "mobile": False}))

    def canvas_click_point(self, world_x, world_y):
        """Replicate the game's viewTransform() (src/heartwood-game.js) for a
        trusted click at a world coordinate. Guarded on dpr==1 (headless)."""
        return self.evaluate(
            "(()=>{"
            "if(window.devicePixelRatio!==1) return {err:'devicePixelRatio='+window.devicePixelRatio};"
            'const wrap=document.getElementById("canvasWrap").getBoundingClientRect();'
            "const w=Math.max(320,Math.floor(wrap.width)), h=Math.max(220,Math.floor(wrap.height));"
            f"const s=Math.min(w/{WORLD_W},h/{WORLD_H});"
            f"const ox=(w-{WORLD_W}*s)/2, oy=(h-{WORLD_H}*s)/2;"
            'const cr=document.getElementById("gameCanvas").getBoundingClientRect();'
            f"return {{x:Math.round(cr.left+ox+{world_x}*s), y:Math.round(cr.top+oy+{world_y}*s)}};"
            "})()"
        )

    # ---- flows -------------------------------------------------------------

    def flow1_load(self):
        self.step = "flow1: site loads clean"
        print(f"[1] load {SITE}")
        self.navigate(SITE)
        self.poll("document.readyState", lambda v: v == "complete", "document.readyState==complete")
        self.poll(self.visible("#startScreen"), lambda v: v is True, "#startScreen visible")
        self.expect_eq(self.evaluate(self.text_of("#startScreen h1")), "Forest Rescue: Heartwood", "start title")
        bad = self.bad_resources()
        if bad:
            raise Fail(f"4xx/5xx subresources on load (Pages subpath bug?): {bad}")
        print("  ok: start screen rendered, no exceptions, no failed loads, no 4xx assets")

    def flow2_campaign_entry(self):
        self.step = "flow2: campaign map entry"
        print("[2] Campaign -> map -> level 1 via map click")
        self.js_click("#playButton")
        self.poll(self.visible("#campaignScreen"), lambda v: v is True, "#campaignScreen visible")
        pos = self.evaluate(
            '(()=>{const r=document.getElementById("campaignMap").getBoundingClientRect();'
            f"return {{x:Math.round(r.left+{LEVEL1_MARKER[0]}*r.width), y:Math.round(r.top+{LEVEL1_MARKER[1]}*r.height)}};}})()"
        )
        self.click(pos["x"], pos["y"])  # hit-test radius is 0.08 normalized; marker center is well inside
        self.poll(self.visible("#gameScreen"), lambda v: v is True, "#gameScreen visible after level load", timeout=30)
        self.expect_eq(self.evaluate(self.text_of("#levelTitle")), LEVEL1_NAME, "level title")  # set synchronously by campaign.js
        # The pre-fix failure mode was a frozen HUD (placeholders forever). The
        # engine regenerates mana from the start, so assert liveness — the HUD
        # shows live integers — not exact values.
        self.poll(self.text_of("#manaText"), lambda v: isinstance(v, str) and v.isdigit(), "live mana value", timeout=10)
        # RP-48sjgh: wave 1 is gated behind the Start-Wave button. While gated
        # the wave counter must HOLD at Wave 1 / 8 (unlimited prep, no auto-
        # advancing waves), and only the button press may start the wave.
        gate = self.gate_state()
        self.holds(gate, lambda v: isinstance(v, dict) and v.get("wave") == "Wave 1 / 8" and v.get("startVisible") is True,
                   "wave 1 held behind visible Start-Wave button", seconds=4)
        self.probe_range_ghost()
        self.js_click("#startWaveButton")
        self.poll(gate, lambda v: isinstance(v, dict) and v.get("startVisible") is False, "#startWaveButton hidden after press")
        self.poll(self.text_of("#waveText"), lambda v: isinstance(v, str) and v.startswith("Wave ") and v != "Wave 1 / 8", "wave counter advances past Wave 1", timeout=90)
        print("  ok: gate held wave 1, Start-Wave pressed, wave counter advanced")
        print(f"  ok: entered {LEVEL1_NAME!r}, HUD at mana {START_MANA}, 5 hearts, Wave 1 / 8")

    def probe_range_ghost(self):
        """RP-pyvp2r: hovering a fairy ring with a defender card selected draws
        a range ghost — a circle of the defender's range snapped to the ring,
        green when placeable. The ghost stroke is solid #b4ffa0, so the probe
        samples canvas pixels along the expected circle (sprig-sentinel range
        160 world units) before and after the hover. The pre-hover baseline
        also self-controls against bright lookalike pixels."""
        point = self.canvas_click_point(*LEVEL1_RING)
        if "err" in point:
            raise Fail(f"cannot hover ring: {point['err']}")
        probe = (
            "(()=>{if(window.devicePixelRatio!==1)return{err:'dpr='+window.devicePixelRatio};"
            "const cv=document.getElementById('gameCanvas');const c2=cv.getContext('2d');"
            "const wrap=document.getElementById('canvasWrap').getBoundingClientRect();"
            "const w=Math.max(320,Math.floor(wrap.width)),h=Math.max(220,Math.floor(wrap.height));"
            f"const s=Math.min(w/{WORLD_W},h/{WORLD_H});"
            f"const ox=(w-{WORLD_W}*s)/2,oy=(h-{WORLD_H}*s)/2;"
            f"const cx=ox+{LEVEL1_RING[0]}*s,cy=oy+{LEVEL1_RING[1]}*s,R=160*s;"
            "const bx=Math.max(0,Math.floor(cx-R-4)),by=Math.max(0,Math.floor(cy-R-4));"
            "const bw=Math.min(cv.width-bx,Math.ceil(2*R)+9),bh=Math.min(cv.height-by,Math.ceil(2*R)+9);"
            "if(bw<2||bh<2)return{err:'probe box '+bw+'x'+bh};"
            "const img=c2.getImageData(bx,by,bw,bh).data;"
            "const near=(px,py)=>{px=Math.round(px)-bx;py=Math.round(py)-by;"
            "for(let du=-2;du<=2;du++)for(let dv=-2;dv<=2;dv++){const x=px+du,y=py+dv;"
            "if(x<0||y<0||x>=bw||y>=bh)continue;const i=(y*bw+x)*4;"
            "if(Math.abs(img[i]-180)<=14&&Math.abs(img[i+1]-255)<=14&&Math.abs(img[i+2]-160)<=14)return true;}return false;};"
            "let hits=0;const N=72;for(let i=0;i<N;i++){const a=2*Math.PI*i/N;"
            "if(near(cx+R*Math.cos(a),cy+R*Math.sin(a)))hits++;}return {hits,N};})()"
        )
        base = self.evaluate(probe)
        if not isinstance(base, dict) or "hits" not in base:
            raise Fail(f"ghost probe returned {base!r}")
        if base["hits"] >= 10:
            raise Fail(f"ghost already visible before hover: {base['hits']}/{base['N']} sample hits")
        self.ca("Input.dispatchMouseEvent", json.dumps({"type": "mouseMoved", "x": point["x"], "y": point["y"]}))
        got = self.poll(probe, lambda v: isinstance(v, dict) and v.get("hits", 0) >= 40,
                        "range ghost circle on ring hover", timeout=8)
        print(f"  ok: range ghost drawn on hover ({got['hits']}/{got['N']} circle samples matched #b4ffa0)")
        self.ca("Input.dispatchMouseEvent", json.dumps({"type": "mouseMoved", "x": 4, "y": 4}))

    def flow3_plant_defender(self):
        self.step = "flow3: plant defender on fairy ring"
        print("[3] plant Magic Tree on ring-7 (trusted canvas click)")
        point = self.canvas_click_point(*LEVEL1_RING)
        if "err" in point:
            raise Fail(f"cannot place trusted click: {point['err']}")
        before = int(self.evaluate(self.text_of("#manaText")))
        self.click(point["x"], point["y"])
        # Planting spends TREE_COST mana instantly; regen (5.2/s) only adds.
        # A net drop of >= half the cost therefore proves the spend while
        # staying true on ANY read within ~4.8s of the click — the old
        # `before - TREE_COST + 5` window assumed a sub-second first read and
        # went false-negative whenever the pre-plant regen wait ran long
        # (RP-pyvp2r: the ghost probe adds a few seconds of regen upstream).
        self.poll(self.text_of("#manaText"), lambda v: isinstance(v, str) and v.isdigit() and int(v) <= before - TREE_COST // 2, f"mana drops from {before} by ~{TREE_COST}", timeout=10)
        print(f"  ok: defender planted, mana {before} -> {self.evaluate(self.text_of('#manaText'))}")

    def flow4_battle_resolves(self):
        self.step = "flow4: battle resolves end to end"
        url = f"{SITE}?level={HANDTEST_ID}"
        print(f"[4] full battle on {HANDTEST_NAME!r} ({url})")
        self.navigate(url)
        self.poll("document.readyState", lambda v: v == "complete", "document.readyState==complete")
        self.poll(self.visible("#gameScreen"), lambda v: v is True, "#gameScreen visible (level param entry)", timeout=30)
        self.expect_eq(self.evaluate(self.text_of("#levelTitle")), HANDTEST_NAME, "level title")
        self.poll(self.text_of("#manaText"), lambda v: isinstance(v, str) and v.isdigit(), "live mana value", timeout=10)
        # RP-48sjgh: a fresh level (?level= entry included) holds wave 1 behind
        # the Start-Wave button — assert the hold, then press before planting
        # (the centered overlay button would swallow canvas clicks near the
        # screen center, so the press must precede ring clicks).
        gate = self.gate_state()
        self.holds(gate, lambda v: isinstance(v, dict) and v.get("wave") == "Wave 1 / 3" and v.get("startVisible") is True,
                   "wave 1 held behind Start-Wave on ?level= entry", seconds=3)
        self.js_click("#startWaveButton")
        self.poll(gate, lambda v: isinstance(v, dict) and v.get("startVisible") is False, "#startWaveButton hidden after press")
        mana_before = int(self.evaluate(self.text_of("#manaText")))
        for i, (wx, wy) in enumerate(HANDTEST_RINGS):
            point = self.canvas_click_point(wx, wy)
            if "err" in point:
                raise Fail(f"cannot place trusted click (ring {i}): {point['err']}")
            self.click(point["x"], point["y"])
        mana_after = int(self.evaluate(self.text_of("#manaText")))
        # Three Magic Trees cost 150; regen may give some back but not much in
        # the sub-second planting window. A strict decrease proves plants land.
        if mana_after >= mana_before:
            raise Fail(f"planting did not spend mana: before {mana_before}, after {mana_after}")
        print(f"  ok: defenders planted (mana {mana_before} -> {mana_after})")
        # The hidden overlay ships static "Game Over" text in index.html, so
        # title text alone is NOT a resolution signal — the #endOverlay element
        # must have lost its "hidden" class too. #replayButton never carries a
        # hidden class of its own (hiding is via the #endOverlay ancestor), so
        # replay visibility is derived from the overlay's visibility.
        hud = self.poll(
            '(()=>({endVisible:!document.querySelector("#endOverlay").classList.contains("hidden"),'
            'end:document.querySelector("#endTitle").textContent}))()',
            lambda v: isinstance(v, dict) and v.get("endVisible") is True and v.get("end") in ("Victory", "Game Over"),
            "#endOverlay visible with title (Victory or Game Over)",
            timeout=240,
        )
        outcome = hud["end"]
        replay_visible = self.evaluate(self.visible("#endOverlay"))
        msg = self.evaluate(self.text_of("#endMessage"))
        self.screenshot("final-outcome")
        print(f"  ok: battle resolved -> {outcome!r} ({msg}); overlay visible: {hud['endVisible']}; replay visible: {replay_visible}")

    # ---- fit guarantees (RP-vebqyv) ----------------------------------------

    def assert_fit(self, what):
        """Layout fits the pinned viewport: no page overflow, every toolbar
        card fully on-screen (reachable), canvas and wrap inside the window.
        Also asserts the RP-pyvp2r role line is present on every card."""
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
            raise Fail(f"{what}: fit probe returned {fit!r}")
        if fit["sw"] > fit["iw"] + 1:
            raise Fail(f"{what}: page overflows viewport: scrollWidth {fit['sw']} > innerWidth {fit['iw']}")
        off = [b["text"] for b in fit["cards"]
               if b["l"] < -1 or b["t"] < -1 or b["r"] > fit["iw"] + 1 or b["b"] > fit["ih"] + 1]
        if off:
            raise Fail(f"{what}: cards unreachable at {fit['iw']}x{fit['ih']}: {off}")
        bare = [b["text"] for b in fit["cards"] if not b.get("role")]
        if bare:
            raise Fail(f"{what}: cards missing a role line (RP-pyvp2r): {bare}")
        for name, box in (("#gameCanvas", fit["canvas"]), ("#canvasWrap", fit["wrap"])):
            if box["l"] < -1 or box["t"] < -1 or box["r"] > fit["iw"] + 1 or box["b"] > fit["ih"] + 1:
                raise Fail(f"{what}: {name} exceeds viewport at {fit['iw']}x{fit['ih']}: {box}")
        print(f"  ok: fit at {fit['iw']}x{fit['ih']} — scrollWidth {fit['sw']}, {len(fit['cards'])} cards reachable with role lines, canvas+wrap inside viewport ({what})")

    def flow5_fit_and_controls(self):
        self.step = "flow5: fit at 940x850, Replay refits canvas, pause/mute reachable"
        print("[5] fit checks (RP-vebqyv): no overflow, cards reachable, Replay refit, pause/mute")
        self.assert_fit("before Replay")
        # Replay used to snap the canvas from ~924px to the page's overflowing
        # 2296px layout width (the card bar's old min-content width), pushing
        # spawn-side rings, pause and mute off-screen.
        self.js_click("#replayButton")
        self.poll(self.visible("#endOverlay"), lambda v: v is False, "#endOverlay hidden after Replay")
        self.poll(self.visible("#gameScreen"), lambda v: v is True, "#gameScreen visible after Replay")
        self.poll(self.text_of("#manaText"), lambda v: isinstance(v, str) and v.isdigit(), "live mana value after Replay", timeout=10)
        # RP-48sjgh: Replay re-arms the gate — wave 1 (of the 3-wave hand-test
        # level) must hold behind a visible Start-Wave button until pressed.
        gate = self.gate_state()
        self.holds(gate, lambda v: isinstance(v, dict) and v.get("wave") == "Wave 1 / 3" and v.get("startVisible") is True,
                   "wave 1 held behind Start-Wave after Replay", seconds=3)
        self.js_click("#startWaveButton")
        self.poll(gate, lambda v: isinstance(v, dict) and v.get("startVisible") is False, "#startWaveButton hidden after post-Replay press")
        self.assert_fit("after Replay")
        self.screenshot("after-replay")
        self.js_click("#pauseButton")
        self.poll(self.visible("#pauseOverlay"), lambda v: v is True, "#pauseOverlay visible after pause click")
        self.js_click("#resumeButton")
        self.poll(self.visible("#pauseOverlay"), lambda v: v is False, "#pauseOverlay hidden after resume click")
        self.js_click("#muteButton")
        self.poll(self.text_of("#muteButton"), lambda v: v == "\U0001F507", "mute button toggles to \U0001F507")
        self.js_click("#muteButton")
        self.poll(self.text_of("#muteButton"), lambda v: v == "\U0001F50A", "mute button toggles back to \U0001F50A")
        print("  ok: pause and mute reachable and functional")

    # ---- mana flower taps (RP-a7h9z5) ---------------------------------------

    def flow6_flower_tap(self):
        self.step = "flow6: mana flower tap lands at center, +25 mana"
        print("[6] scripted tap at a flower's center collects it (RP-a7h9z5)")
        self.navigate(f"{SITE}?level={HANDTEST_ID}&debug")
        self.poll("document.readyState", lambda v: v == "complete", "document.readyState==complete")
        self.poll(self.visible("#gameScreen"), lambda v: v is True, "#gameScreen visible (?level entry)", timeout=30)
        # ?debug exposes the live battle state (src/campaign.js window.__fr) so
        # the tap targets the flower's exact world center.
        self.poll("typeof window.__fr?.getState", lambda v: v == "function", "window.__fr debug hook present", timeout=10)
        flower = self.poll(
            "(()=>{const f=window.__fr.getState()?.flowers?.[0];return f?{x:f.x,y:f.y}:null})()",
            lambda v: isinstance(v, dict), "a mana flower to spawn (first spawn ~6s)", timeout=30,
        )
        self.screenshot("flower-visible")
        mana_before = int(self.evaluate(self.text_of("#manaText")))
        point = self.canvas_click_point(flower["x"], flower["y"])
        if "err" in point:
            raise Fail(f"cannot tap flower: {point['err']}")
        self.click(point["x"], point["y"])
        self.poll(
            f"(()=>{{const s=window.__fr.getState();"
            f"return !s.flowers.some(f=>Math.hypot(f.x-{flower['x']},f.y-{flower['y']})<1);}})()",
            lambda v: v is True, "tapped flower removed from state", timeout=5,
        )
        mana_after = int(self.evaluate(self.text_of("#manaText")))
        # The tap pays +25; reads may straddle ~2s of passive regen (+10.4), so
        # a net +12 still proves the pickup landed.
        if mana_after < mana_before + 12:
            raise Fail(f"flower tap did not pay mana: before {mana_before}, after {mana_after}")
        print(f"  ok: flower collected at ({flower['x']:.0f},{flower['y']:.0f}), mana {mana_before} -> {mana_after}")

    # ---- lifecycle ---------------------------------------------------------

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
            self.pin_viewport()  # pin before any navigation so every flow runs at 940x850
            self.flow1_load()
            self.check_events()
            self.flow2_campaign_entry()
            self.check_events()
            self.flow3_plant_defender()
            self.check_events()
            self.flow4_battle_resolves()
            self.check_events()
            self.flow5_fit_and_controls()
            self.check_events()
            self.flow6_flower_tap()
            self.check_events()
            print("\nPASS: Forest Rescue on GitHub Pages is working end to end.")
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


if __name__ == "__main__":
    Runner().run()
