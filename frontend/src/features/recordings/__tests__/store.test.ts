import { beforeEach, describe, expect, it } from "vitest";
import { useRecordingsStore } from "../store";

const DISPLAYED = ["a", "b", "c", "d"];
const store = () => useRecordingsStore.getState();

beforeEach(() => {
  store().clearChecked();
});

describe("useRecordingsStore range selection", () => {
  it("selects the range between a plain click and a Shift+click", () => {
    store().toggleCheck("a");
    store().checkRange(DISPLAYED, "c");

    expect(store().checkedFolders).toEqual(new Set(["a", "b", "c"]));
    expect(store().anchorFolder).toBe("a");
  });

  it("deselects the range when the anchor was just unchecked", () => {
    store().setCheckedFolders(DISPLAYED);
    store().toggleCheck("b");
    store().checkRange(DISPLAYED, "d");

    expect(store().checkedFolders).toEqual(new Set(["a"]));
  });

  it("treats a Shift+click without an anchor as a plain click that sets the anchor", () => {
    store().checkRange(DISPLAYED, "b");
    expect(store().checkedFolders).toEqual(new Set(["b"]));
    expect(store().anchorFolder).toBe("b");

    store().checkRange(DISPLAYED, "d");
    expect(store().checkedFolders).toEqual(new Set(["b", "c", "d"]));
  });

  it("drops the anchor when the selection is replaced", () => {
    store().toggleCheck("a");
    store().toggleCheckAll(DISPLAYED);
    expect(store().anchorFolder).toBeNull();

    store().toggleCheck("a");
    store().setCheckedFolders(["b"]);
    expect(store().anchorFolder).toBeNull();

    store().toggleCheck("a");
    store().clearChecked();
    expect(store().anchorFolder).toBeNull();
  });
});
