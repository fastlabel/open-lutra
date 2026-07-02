import { beforeEach, describe, expect, it } from "vitest";
import { TOAST_DURATION_MS, TOAST_LIMIT, toast, useToastStore } from "../toast-store";

describe("useToastStore", () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
  });

  describe("add", () => {
    it("pushes a toast and returns its id", () => {
      const id = useToastStore.getState().add({ title: "Hello", variant: "info", duration: 1000 });

      const { toasts } = useToastStore.getState();
      expect(toasts).toHaveLength(1);
      expect(toasts[0]).toMatchObject({ id, title: "Hello", variant: "info", duration: 1000 });
    });

    it("assigns a unique id to each toast", () => {
      const first = useToastStore.getState().add({ title: "a", variant: "info", duration: 1000 });
      const second = useToastStore.getState().add({ title: "b", variant: "info", duration: 1000 });

      expect(first).not.toBe(second);
    });

    it("caps the stack at TOAST_LIMIT, dropping the oldest", () => {
      for (let i = 0; i < TOAST_LIMIT + 2; i++) {
        useToastStore.getState().add({ title: `t${i}`, variant: "info", duration: 1000 });
      }

      const { toasts } = useToastStore.getState();
      expect(toasts).toHaveLength(TOAST_LIMIT);
      expect(toasts[0].title).toBe("t2");
      expect(toasts[TOAST_LIMIT - 1].title).toBe(`t${TOAST_LIMIT + 1}`);
    });
  });

  describe("remove", () => {
    it("removes the toast with the given id and leaves the rest", () => {
      const keep = useToastStore.getState().add({ title: "keep", variant: "info", duration: 1000 });
      const drop = useToastStore.getState().add({ title: "drop", variant: "info", duration: 1000 });

      useToastStore.getState().remove(drop);

      const { toasts } = useToastStore.getState();
      expect(toasts).toHaveLength(1);
      expect(toasts[0].id).toBe(keep);
    });
  });

  describe("toast helper", () => {
    it("success adds a success toast with the default duration", () => {
      toast.success("Done", "details");

      expect(useToastStore.getState().toasts[0]).toMatchObject({
        title: "Done",
        description: "details",
        variant: "success",
        duration: TOAST_DURATION_MS,
      });
    });

    it("error adds an error toast", () => {
      toast.error("Boom");

      expect(useToastStore.getState().toasts[0]).toMatchObject({ title: "Boom", variant: "error" });
    });

    it("info adds an info toast", () => {
      toast.info("FYI");

      expect(useToastStore.getState().toasts[0]).toMatchObject({ title: "FYI", variant: "info" });
    });
  });
});
