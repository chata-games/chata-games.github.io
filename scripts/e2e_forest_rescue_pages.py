#!/usr/bin/env python3
"""Smoke-test the deployed Forest Rescue Phaser app with chrome-agent."""

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

SITE = os.environ.get("FR_E2E_SITE", "https://chata-games.github.io/forest-rescue/")
PROFILES = {
    "desktop": {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False},
    "phone": {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
}


class Failure(RuntimeError):
    pass


class Browser:
    def __init__(self):
        self.name = ""
        self.attach = None
        fd, events_path = tempfile.mkstemp(prefix="fr-pages-events-", suffix=".jsonl")
        os.close(fd)
        self.events_path = Path(events_path)
        self.event_offset = 0

    def command(self, args, timeout=30):
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise Failure(f"{' '.join(args[:3])} failed: {result.stderr.strip()[:500]}")
        return result.stdout

    def launch(self):
        data = json.loads(self.command(["chrome-agent", "launch", "--headless"]))
        self.name = data["name"]
        event_file = self.events_path.open("w", encoding="utf-8")
        self.attach = subprocess.Popen(
            ["chrome-agent", "attach", self.name, "+Page.loadEventFired",
             "+Runtime.exceptionThrown", "+Runtime.consoleAPICalled", "+Network.loadingFailed"],
            stdout=event_file, stderr=subprocess.STDOUT, text=True,
        )
        event_file.close()

    def cdp(self, method, params=None):
        raw = self.command(["chrome-agent", self.name, method, json.dumps(params or {})])
        return json.loads(raw)

    def evaluate(self, expression):
        data = self.cdp("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if data.get("exceptionDetails"):
            raise Failure(f"page evaluation failed: {data['exceptionDetails']}")
        return data.get("result", {}).get("value")

    def poll(self, expression, predicate, label, timeout=15):
        deadline = time.monotonic() + timeout
        observed = None
        while time.monotonic() < deadline:
            observed = self.evaluate(expression)
            if predicate(observed):
                return observed
            self.check_events()
            time.sleep(0.1)
        raise Failure(f"Timed out waiting for {label}. Observed: {observed!r}")

    def click(self, selector):
        point = self.evaluate(
            "(()=>{const e=document.querySelector(" + json.dumps(selector) + ");"
            "if(!e)return null;const r=e.getBoundingClientRect();"
            "return{x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)}})()"
        )
        if not point:
            raise Failure(f"Cannot find click target: {selector}")
        for event_type in ("mousePressed", "mouseReleased"):
            self.cdp("Input.dispatchMouseEvent", {
                "type": event_type, "x": point["x"], "y": point["y"],
                "button": "left", "clickCount": 1,
            })

    def expect(self, expression, expected, label):
        observed = self.evaluate(expression)
        if observed != expected:
            raise Failure(f"{label}: expected {expected!r}, observed {observed!r}")

    def check_events(self):
        with self.events_path.open(encoding="utf-8") as event_file:
            event_file.seek(self.event_offset)
            lines = event_file.readlines()
            self.event_offset = event_file.tell()
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            method = event.get("method")
            params = event.get("params", {})
            if method == "Network.loadingFailed":
                if params.get("canceled") or "ERR_ABORTED" in params.get("errorText", ""):
                    continue
                raise Failure(f"Network load failed: {params}")
            if method == "Runtime.exceptionThrown":
                raise Failure(f"Page exception: {params}")
            if method == "Runtime.consoleAPICalled" and params.get("type") == "error":
                raise Failure(f"Console error: {params.get('args', [])}")

    def screenshot(self, path):
        data = self.cdp("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        Path(path).write_bytes(base64.b64decode(data["data"]))

    def stop(self):
        if self.attach:
            self.attach.terminate()
            try:
                self.attach.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.attach.kill()
        if self.name:
            subprocess.run(["chrome-agent", "stop", self.name], capture_output=True, text=True)
            status = subprocess.run(["chrome-agent", "status"], capture_output=True, text=True)
            if self.name in status.stdout:
                raise Failure(f"chrome-agent instance still running: {self.name}")
        self.events_path.unlink(missing_ok=True)


def dismiss_if_visible(browser, selector):
    visible = browser.evaluate(
        "(()=>{const e=document.querySelector(" + json.dumps(selector) + ");return !!e&&e.getClientRects().length>0})()"
    )
    if visible:
        browser.click(selector)
        browser.poll(
            "document.querySelector(" + json.dumps(selector) + ").closest('[role=dialog],section').hidden",
            lambda value: value is True, f"{selector} dismissal",
        )


def run_profile(browser, label, metrics):
    browser.cdp("Emulation.setDeviceMetricsOverride", metrics)
    browser.cdp("Page.navigate", {"url": SITE})
    browser.poll("document.readyState", lambda value: value == "complete", "document load")
    browser.poll("document.querySelectorAll('.trail-node').length", lambda value: value and value > 0, "campaign nodes")
    browser.expect("document.title.includes('Forest Rescue')", True, "page title")
    browser.expect("document.querySelector('vite-error-overlay') === null", True, "no build error overlay")
    browser.evaluate("window.fr?.clearSave()")

    browser.click(".trail-node[data-level='01-meadows-edge']")
    browser.poll("document.querySelector('#trailDetail').open", bool, "level detail")
    browser.click("#detailEnter")
    browser.poll("!document.querySelector('#loadoutScreen').hidden", bool, "loadout")
    browser.expect("document.querySelector('#loadoutStart').disabled", False, "starter loadout")
    browser.poll(
        "[...document.querySelectorAll('#loadoutScreen img')].some(i=>i.complete&&i.naturalWidth>0)",
        bool, "loadout art",
    )

    browser.click("#loadoutStart")
    browser.poll("!document.querySelector('#battleRoot').hidden", bool, "battle")
    dismiss_if_visible(browser, "#storySkip")
    dismiss_if_visible(browser, "#tutorialSkip")
    dismiss_if_visible(browser, "#portraitAdviceKeep")
    browser.poll("document.querySelector('#game-root canvas')?.width", lambda value: value and value > 0, "Phaser canvas")
    browser.expect("document.querySelector('#manaValue').textContent.trim()", "150", "starting mana")
    browser.expect(
        "(()=>{const c=document.querySelector('#game-root canvas').getBoundingClientRect();"
        "const p=document.querySelector('#game-root').getBoundingClientRect();"
        "return Math.abs(c.left+c.width/2-p.left-p.width/2)<2"
        "&& c.left>=p.left-1 && c.right<=p.right+1"
        "&& Math.abs(c.width/c.height-1.5)<0.02})()",
        True, "complete centered battlefield",
    )

    browser.click("[data-defender='sprig-sentinel']")
    browser.expect("document.querySelector('[data-defender=\"sprig-sentinel\"]').getAttribute('aria-pressed')", "true", "Sprig selection")
    browser.evaluate("window.fr.placeOnRing(window.fr.ringIds()[0])")
    browser.poll("document.querySelector('#manaValue').textContent.trim()", lambda value: value == "100", "Sprig placement")

    browser.click("#startBtn")
    browser.poll("document.querySelector('#pauseBtn').disabled", lambda value: value is False, "wave start")
    browser.click("#pauseBtn")
    browser.poll("!document.querySelector('#pauseOverlay').hidden", bool, "pause overlay")
    browser.expect("document.querySelector('#pauseBtn').getAttribute('aria-pressed')", "true", "paused state")
    browser.click("#resumeBtn")
    browser.poll("document.querySelector('#pauseOverlay').hidden", bool, "resume")
    browser.expect("document.querySelector('#pauseBtn').getAttribute('aria-pressed')", "false", "resumed state")

    failed_assets = browser.evaluate(
        "performance.getEntriesByType('resource')"
        ".filter(e=>e.responseStatus>=400&&!/favicon\\.ico(?:$|\\?)/.test(e.name))"
        ".map(e=>e.name)"
    )
    if failed_assets:
        raise Failure(f"Assets returned HTTP errors: {failed_assets}")
    browser.check_events()
    print(f"PASS {label}: art, placement, pause, resume, centered battlefield, clean network")


def main():
    browser = Browser()
    try:
        browser.launch()
        for label, metrics in PROFILES.items():
            run_profile(browser, label, metrics)
    except Exception as error:
        if browser.name:
            try:
                browser.screenshot("/tmp/forest-rescue-pages-failure.png")
            except Exception:
                pass
        print(f"FAIL: {error}")
        return 1
    finally:
        browser.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
