const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../flashcards/static/flashcards/app.js"), "utf8");

function setup(keys = [" ", "1", "2", "u"]) {
  const listeners = {};
  const submissions = [];
  const form = {requestSubmit(button) {
    let cancelled = false;
    listeners.submit({preventDefault() { cancelled = true; }});
    if (!cancelled) submissions.push(button.dataset.studyKey);
  }};
  const controls = {
    addEventListener(name, handler) { listeners[name] = handler; },
    querySelectorAll() { return keys.map(key => ({dataset: {studyKey: key}, form})); },
  };
  const document = {
    querySelector(selector) { return selector === "[data-study-controls]" ? controls : null; },
    addEventListener(name, handler) { listeners[name] = handler; },
  };
  const window = {addEventListener(name, handler) { listeners[name] = handler; }};
  vm.runInNewContext(source, {document, window});
  return {submissions, listeners, press(key, tag = "body", overrides = {}) {
    let prevented = false;
    listeners.keydown({key, target: {
      isContentEditable: tag === "editable",
      closest(selector) { return selector.split(", ").includes(tag); },
    }, preventDefault() { prevented = true; }, ...overrides});
    return prevented;
  }};
}

test("rating and undo shortcuts work with focused buttons and links", () => {
  for (const tag of ["body", "button", "a"]) {
    for (const key of ["1", "2", "u", "U"]) {
      const page = setup();
      assert.equal(page.press(key, tag, {shiftKey: key === "U"}), true);
      assert.deepEqual(page.submissions, [key.toLowerCase()]);
    }
  }
});

test("Space reveals from the page and preserves focused control activation", () => {
  const page = setup([" "]);
  assert.equal(page.press(" "), true);
  assert.deepEqual(page.submissions, [" "]);
  for (const tag of ["button", "a"]) {
    assert.equal(setup().press(" ", tag), false);
  }
});

test("shortcuts do not interrupt editing, composition, modifiers, or held keys", () => {
  for (const tag of ["input", "textarea", "select", "editable"]) {
    assert.equal(setup().press("1", tag), false);
  }
  for (const flag of ["repeat", "isComposing", "ctrlKey", "altKey", "metaKey"]) {
    const page = setup();
    assert.equal(page.press("1", "body", {[flag]: true}), false);
    assert.deepEqual(page.submissions, []);
  }
  assert.equal(setup([" "]).press("1"), false);
});

test("prevents duplicate submissions and resets after history navigation", () => {
  const page = setup();
  page.press("1");
  page.press("2");
  assert.deepEqual(page.submissions, ["1"]);
  page.listeners.pageshow();
  page.press("u");
  assert.deepEqual(page.submissions, ["1", "u"]);
});
