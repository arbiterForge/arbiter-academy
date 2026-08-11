import test from "node:test";
import assert from "node:assert/strict";

import {
  bindAcademyPage,
  copyCommand,
  restorePreferences,
  selectVariant,
} from "../../site/assets/academy.js";

class FakeElement {
  constructor({ dataset = {}, textContent = "", attributes = {} } = {}) {
    this.dataset = { ...dataset };
    this.textContent = textContent;
    this.attributes = { ...attributes };
    this.hidden = false;
    this.focused = false;
    this.listeners = new Map();
    this.ownerDocument = null;
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }

  focus() {
    this.focused = true;
  }

  async dispatch(name) {
    return this.listeners.get(name)?.({ currentTarget: this, preventDefault() {} });
  }
}

class FakeDocument {
  constructor({ variants = [], buttons = [], osControls = [], hostControls = [], preferenceGroups = [], ids = {} } = {}) {
    this.variants = variants;
    this.buttons = buttons;
    this.osControls = osControls;
    this.hostControls = hostControls;
    this.preferenceGroups = preferenceGroups;
    this.ids = ids;
    this.documentElement = new FakeElement();
    for (const element of [...variants, ...buttons, ...osControls, ...hostControls, ...preferenceGroups, ...Object.values(ids)]) {
      element.ownerDocument = this;
    }
  }

  querySelectorAll(selector) {
    return {
      ".command-variant[data-os][data-host]": this.variants,
      "[data-copy-target]": this.buttons,
      ".academy-os-choice[data-os]": this.osControls,
      ".academy-host-choice[data-host]": this.hostControls,
      ".academy-command-preferences": this.preferenceGroups,
    }[selector] ?? [];
  }

  getElementById(id) {
    return this.ids[id] ?? null;
  }
}

function storageFixture(values = {}) {
  return {
    values: { ...values },
    getItem(key) {
      return this.values[key] ?? null;
    },
    setItem(key, value) {
      this.values[key] = value;
    },
  };
}

function copyFixture(command = "!git remote -v\n") {
  const code = new FakeElement({ textContent: command });
  const status = new FakeElement();
  const button = new FakeElement({
    dataset: { copyTarget: "command-one" },
    attributes: { "aria-describedby": "copy-status-one" },
  });
  new FakeDocument({ buttons: [button], ids: { "command-one": code, "copy-status-one": status } });
  return { button, code, status };
}

test("copyCommand copies exactly the target textContent bytes", async () => {
  const fixture = copyFixture();
  const copied = [];
  await copyCommand(
    fixture.button,
    { writeText: async (value) => copied.push(value) },
    { selectNodeContents() { assert.fail("fallback must not run"); } },
  );
  assert.deepEqual(copied, ["!git remote -v\n"]);
  assert.equal(fixture.status.textContent, "Copied command.");
});

test("copyCommand selects and focuses exact command after clipboard rejection", async () => {
  const fixture = copyFixture("git status\n");
  const selected = [];
  await copyCommand(
    fixture.button,
    { writeText: async () => { throw new Error("denied"); } },
    { selectNodeContents: (target) => { selected.push(target); return true; } },
  );
  assert.equal(fixture.code.focused, true);
  assert.deepEqual(selected, [fixture.code]);
  assert.equal(
    fixture.status.textContent,
    "Clipboard unavailable. The command is selected; press Ctrl+C or Command+C.",
  );
});

test("copyCommand reports truthful manual-copy guidance when selection is unavailable", async () => {
  for (const selection of [
    undefined,
    { selectNodeContents() { return false; } },
    { selectNodeContents() { throw new Error("selection denied"); } },
  ]) {
    const fixture = copyFixture("git status\n");
    await copyCommand(
      fixture.button,
      { writeText: async () => { throw new Error("clipboard denied"); } },
      selection,
    );
    assert.equal(fixture.code.focused, true);
    assert.equal(
      fixture.status.textContent,
      "Clipboard unavailable. Focus is on the command; select its text and press Ctrl+C or Command+C.",
    );
  }
});

test("copyCommand reports a missing target without touching clipboard", async () => {
  const status = new FakeElement();
  const button = new FakeElement({
    dataset: { copyTarget: "missing-command" },
    attributes: { "aria-describedby": "copy-status-one" },
  });
  new FakeDocument({ buttons: [button], ids: { "copy-status-one": status } });
  let writes = 0;
  await copyCommand(button, { writeText: async () => { writes += 1; } }, { selectNodeContents() {} });
  assert.equal(writes, 0);
  assert.equal(status.textContent, "Command unavailable.");
});

test("selectVariant filters with independent OS and host wildcards without deleting variants", () => {
  const variants = [
    new FakeElement({ dataset: { os: "windows", host: "none" } }),
    new FakeElement({ dataset: { os: "windows", host: "codex" } }),
    new FakeElement({ dataset: { os: "all", host: "none" } }),
    new FakeElement({ dataset: { os: "linux", host: "codex" } }),
    new FakeElement({ dataset: { os: "windows", host: "pi" } }),
  ];
  const root = new FakeDocument({ variants });
  selectVariant(root, "windows", "codex");
  assert.deepEqual(variants.map((variant) => variant.hidden), [false, false, false, true, true]);
  assert.equal(root.variants.length, 5);

  selectVariant(root, "linux", "codex");
  assert.deepEqual(variants.map((variant) => variant.hidden), [true, true, false, false, true]);

  selectVariant(root, "windows", null);
  assert.deepEqual(variants.map((variant) => variant.hidden), [false, false, false, true, false]);
  selectVariant(root, null, "codex");
  assert.deepEqual(variants.map((variant) => variant.hidden), [false, false, false, false, true]);
});

test("restorePreferences rejects incomplete, malformed, or unknown stored choices", () => {
  assert.deepEqual(restorePreferences(storageFixture()), { os: null, host: null });
  assert.deepEqual(
    restorePreferences(storageFixture({ "academy-os": "windows", "academy-host": "unknown" })),
    { os: "windows", host: null },
  );
  assert.deepEqual(
    restorePreferences(storageFixture({ "academy-os": "WINDOWS", "academy-host": "codex" })),
    { os: null, host: "codex" },
  );
  assert.deepEqual(
    restorePreferences(storageFixture({ "academy-os": "linux", "academy-host": "pi" })),
    { os: "linux", host: "pi" },
  );
});

test("restorePreferences fails closed when storage cannot be read", () => {
  assert.deepEqual(
    restorePreferences({ getItem() { throw new Error("blocked"); } }),
    { os: null, host: null },
  );
});

test("bindAcademyPage binds before enhancing and applies only complete preferences", async () => {
  const variants = [
    new FakeElement({ dataset: { os: "windows", host: "none" } }),
    new FakeElement({ dataset: { os: "linux", host: "pi" } }),
  ];
  const fixture = copyFixture("echo safe\n");
  const document = new FakeDocument({
    variants,
    buttons: [fixture.button],
    ids: { "command-one": fixture.code, "copy-status-one": fixture.status },
  });
  const storage = storageFixture({ "academy-os": "windows", "academy-host": "codex" });
  const copied = [];
  bindAcademyPage(document, { clipboard: { writeText: async (value) => copied.push(value) } }, storage);

  assert.equal(document.documentElement.dataset.enhanced, "true");
  assert.deepEqual(variants.map((variant) => variant.hidden), [false, true]);
  await fixture.button.dispatch("click");
  assert.deepEqual(copied, ["echo safe\n"]);
});

test("bindAcademyPage leaves every no-preference variant exposed", () => {
  const variants = [
    new FakeElement({ dataset: { os: "windows", host: "none" } }),
    new FakeElement({ dataset: { os: "linux", host: "pi" } }),
  ];
  const osControl = new FakeElement({ dataset: { os: "windows" }, attributes: { "aria-pressed": "false" } });
  const document = new FakeDocument({ variants, osControls: [osControl] });
  bindAcademyPage(document, {}, storageFixture({ "academy-os": "windows" }));
  assert.deepEqual(variants.map((variant) => variant.hidden), [false, true]);
  assert.equal(osControl.getAttribute("aria-pressed"), "true");
  assert.equal(document.documentElement.dataset.enhanced, "true");
});

test("bound OS and host controls persist independent choices before filtering", async () => {
  const variants = [
    new FakeElement({ dataset: { os: "windows", host: "none" } }),
    new FakeElement({ dataset: { os: "windows", host: "codex" } }),
    new FakeElement({ dataset: { os: "linux", host: "pi" } }),
  ];
  const osControl = new FakeElement({ dataset: { os: "windows" } });
  const hostControl = new FakeElement({ dataset: { host: "codex" } });
  const preferences = new FakeElement();
  preferences.hidden = true;
  const document = new FakeDocument({
    variants,
    osControls: [osControl],
    hostControls: [hostControl],
    preferenceGroups: [preferences],
  });
  const storage = storageFixture();
  bindAcademyPage(document, {}, storage);

  assert.equal(preferences.hidden, false);

  await osControl.dispatch("click");
  assert.equal(storage.values["academy-os"], "windows");
  assert.deepEqual(variants.map((variant) => variant.hidden), [false, false, true]);
  await hostControl.dispatch("click");
  assert.equal(storage.values["academy-host"], "codex");
  assert.deepEqual(variants.map((variant) => variant.hidden), [false, false, true]);
  assert.equal(osControl.getAttribute("aria-pressed"), "true");
  assert.equal(hostControl.getAttribute("aria-pressed"), "true");
});

test("bindAcademyPage does not reveal controls or claim enhancement when binding fails", () => {
  const preferences = new FakeElement();
  preferences.hidden = true;
  const brokenButton = new FakeElement({ dataset: { copyTarget: "command-one" } });
  brokenButton.addEventListener = () => { throw new Error("binding failed"); };
  const document = new FakeDocument({ buttons: [brokenButton], preferenceGroups: [preferences] });
  assert.throws(() => bindAcademyPage(document, {}, storageFixture()), /binding failed/);
  assert.equal(preferences.hidden, true);
  assert.equal(document.documentElement.dataset.enhanced, undefined);
});
