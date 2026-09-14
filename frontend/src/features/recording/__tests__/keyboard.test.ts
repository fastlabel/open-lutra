import { afterEach, describe, expect, it } from "vitest";
import { ownsKeyboard } from "../keyboard";

/** Mount an element of the given tag, optionally inside a host, mirroring a page control. */
function mount(tag: string, attributes: Record<string, string> = {}, host: HTMLElement = document.body): HTMLElement {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) el.setAttribute(name, value);
  host.appendChild(el);
  return el;
}

describe("ownsKeyboard", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("yields the key to nothing when there is no focused element", () => {
    expect(ownsKeyboard(null)).toBe(false);
  });

  it("takes the key for a text input", () => {
    expect(ownsKeyboard(mount("input"))).toBe(true);
  });

  it("takes the key for a textarea", () => {
    expect(ownsKeyboard(mount("textarea"))).toBe(true);
  });

  it("takes the key for a contenteditable host", () => {
    expect(ownsKeyboard(mount("div", { contenteditable: "true" }))).toBe(true);
  });

  it('leaves the key to the page for contenteditable="false"', () => {
    expect(ownsKeyboard(mount("div", { contenteditable: "false" }))).toBe(false);
  });

  it("takes the key for a role=textbox host", () => {
    expect(ownsKeyboard(mount("div", { role: "textbox" }))).toBe(true);
  });

  it("takes the key for focus nested inside an open dialog", () => {
    const dialog = mount("div", { role: "dialog" });
    expect(ownsKeyboard(mount("select", {}, dialog))).toBe(true);
  });

  it("takes the key for focus nested inside an alert dialog", () => {
    const dialog = mount("div", { role: "alertdialog" });
    expect(ownsKeyboard(mount("button", {}, dialog))).toBe(true);
  });

  it("leaves the key to the page for a plain button", () => {
    expect(ownsKeyboard(mount("button"))).toBe(false);
  });

  it("leaves the key to the page for a toggle (checkbox / switch render as buttons)", () => {
    expect(ownsKeyboard(mount("button", { role: "switch", "aria-checked": "false" }))).toBe(false);
    expect(ownsKeyboard(mount("button", { role: "checkbox", "aria-checked": "false" }))).toBe(false);
  });

  it("leaves the key to the page for a select, so the delay dropdown does not swallow it", () => {
    expect(ownsKeyboard(mount("select"))).toBe(false);
  });
});
