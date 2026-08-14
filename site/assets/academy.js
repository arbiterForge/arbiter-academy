const OPERATING_SYSTEMS = new Set(["windows", "macos", "linux"]);
const HOSTS = new Set(["claude-code", "codex", "pi"]);

function preference(storage, key, allowed) {
  try {
    const value = storage?.getItem?.(key);
    return allowed.has(value) ? value : null;
  } catch {
    return null;
  }
}

export function restorePreferences(storage) {
  return {
    os: preference(storage, "academy-os", OPERATING_SYSTEMS),
    host: preference(storage, "academy-host", HOSTS),
  };
}

export function selectVariant(root, os, host) {
  if ((os !== null && !OPERATING_SYSTEMS.has(os)) || (host !== null && !HOSTS.has(host))) {
    return;
  }
  for (const variant of root.querySelectorAll(".command-variant[data-os][data-host]")) {
    const osMatches = os === null || variant.dataset.os === "all" || variant.dataset.os === os;
    const hostMatches = host === null || variant.dataset.host === "none" || variant.dataset.host === "selected" || variant.dataset.host === host;
    variant.hidden = !(osMatches && hostMatches);
  }
}

function statusFor(button) {
  const statusId = button.getAttribute("aria-describedby");
  return statusId ? button.ownerDocument?.getElementById(statusId) : null;
}

export async function copyCommand(button, clipboard, selection) {
  const status = statusFor(button);
  const targetId = button.dataset.copyTarget;
  const target = targetId ? button.ownerDocument?.getElementById(targetId) : null;
  if (!target) {
    if (status) {
      status.textContent = "Command unavailable.";
    }
    return;
  }

  try {
    if (typeof clipboard?.writeText !== "function") {
      throw new Error("clipboard unavailable");
    }
    await clipboard.writeText(target.textContent);
    if (status) {
      status.textContent = "Copied command.";
    }
  } catch {
    target.focus();
    let selected = false;
    try {
      selected = selection?.selectNodeContents?.(target) === true;
    } catch {
      selected = false;
    }
    if (status) {
      status.textContent = selected
        ? "Clipboard unavailable. The command is selected; press Ctrl+C or Command+C."
        : "Clipboard unavailable. Focus is on the command; select its text and press Ctrl+C or Command+C.";
    }
  }
}

function selectionAdapter(document) {
  return {
    selectNodeContents(target) {
      const range = document.createRange?.();
      const selection = document.getSelection?.();
      if (!range || !selection) {
        return false;
      }
      try {
        range.selectNodeContents(target);
        selection.removeAllRanges();
        selection.addRange(range);
        return true;
      } catch {
        return false;
      }
    },
  };
}

export function bindAcademyPage(document, navigator, storage) {
  const selection = selectionAdapter(document);
  for (const button of document.querySelectorAll("[data-copy-target]")) {
    button.addEventListener("click", () => copyCommand(button, navigator?.clipboard, selection));
  }

  const preferences = restorePreferences(storage);
  const reflectChoice = (kind, value) => {
    const selector = kind === "os" ? ".academy-os-choice[data-os]" : ".academy-host-choice[data-host]";
    for (const control of document.querySelectorAll(selector)) {
      control.setAttribute("aria-pressed", String(control.dataset[kind] === value));
    }
  };
  const choose = (kind, value) => {
    const allowed = kind === "os" ? OPERATING_SYSTEMS : HOSTS;
    if (!allowed.has(value)) {
      return;
    }
    preferences[kind] = value;
    reflectChoice(kind, value);
    try {
      storage?.setItem?.(`academy-${kind}`, value);
    } catch {
      // A privacy-restricted storage surface must not disable page controls.
    }
    if (preferences.os || preferences.host) {
      selectVariant(document, preferences.os, preferences.host);
    }
  };
  for (const control of document.querySelectorAll(".academy-os-choice[data-os]")) {
    control.addEventListener("click", () => choose("os", control.dataset.os));
  }
  for (const control of document.querySelectorAll(".academy-host-choice[data-host]")) {
    control.addEventListener("click", () => choose("host", control.dataset.host));
  }
  if (preferences.os) {
    reflectChoice("os", preferences.os);
  }
  if (preferences.host) {
    reflectChoice("host", preferences.host);
  }
  if (preferences.os || preferences.host) {
    selectVariant(document, preferences.os, preferences.host);
  }
  for (const group of document.querySelectorAll(".academy-command-preferences")) {
    group.hidden = false;
  }
  document.documentElement.dataset.enhanced = "true";
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  const enhance = () => bindAcademyPage(document, navigator, window.localStorage);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhance, { once: true });
  } else {
    enhance();
  }
}
